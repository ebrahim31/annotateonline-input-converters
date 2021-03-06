from datetime import datetime
import os
import glob
import json
from collections import namedtuple
from tqdm import tqdm
from PIL import Image
from panopticapi.utils import IdGenerator, id2rgb
from .CoCoConverter import CoCoConverter
from .SaPixelToCoco import sa_pixel_to_coco_instance_segmentation, sa_pixel_to_coco_panoptic_segmentation, sa_pixel_to_coco_object_detection
from .SaVectorToCoco import sa_vector_to_coco_instance_segmentation, sa_vector_to_coco_keypoint_detection, sa_vector_to_coco_object_detection

class PanopticConverterStrategy(CoCoConverter):
    name = "Panoptic converter"

    def __init__(self, dataset_name, export_root, project_type, output_dir):
        super().__init__(dataset_name, export_root, project_type, output_dir)
        self.__set_conversion_algorithm()

    def __set_conversion_algorithm(self):

        if self.project_type == 'pixel':
            self.conversion_algorithm = sa_pixel_to_coco_panoptic_segmentation
        elif self.project_type == 'vector':
            pass

    def __str__(self, ):
        return '{} object'.format(self.name)

    def _sa_to_coco_single(self, id_, json_path, id_generator):

        image_commons = self._prepare_single_image_commons(id_, json_path)
        res = self.conversion_algorithm(image_commons, id_generator)

        return res

    def sa_to_output_format(self):

        out_json = self._create_skeleton()
        out_json['categories'] = self._create_categories(
            os.path.join(self.export_root, 'classes_mapper.json')
        )

        panoptic_root = os.path.join(
            self.dataset_name, "panoptic_{}".format(self.dataset_name)
        )

        images = []
        annotations = []
        id_generator = self._make_id_generator()
        jsons = glob.glob(
            os.path.join(self.export_root, '*pixel.json'), recursive=True
        )

        for id_, json_ in tqdm(enumerate(jsons, 1)):
            res = self._sa_to_coco_single(id_, json_, id_generator)

            panoptic_mask = json_[:-len('___pixel.json')] + '.png'

            Image.fromarray(id2rgb(res[2])).save(panoptic_mask)

            annotation = {
                'image_id': res[0]['id'],
                'file_name': panoptic_mask,
                'segments_info': res[1]
            }
            annotations.append(annotation)

            images.append(res[0])

        out_json['annotations'] = annotations
        out_json['images'] = images
        json_data = json.dumps(out_json, indent=4)
        with open(
            os.path.join(self.output_dir, '{}.json'.format(self.dataset_name)),
            'w+'
        ) as coco_json:

            coco_json.write(json_data)

        self.set_num_converted(len(jsons))

class ObjectDetectionStrategy(CoCoConverter):
    name = "ObjectDetection converter"

    def __init__(
        self, dataset_name, export_root, project_type, output_dir, task
    ):
        super().__init__(
            dataset_name, export_root, project_type, output_dir, task
        )
        self.__setup_conversion_algorithm()

    def __setup_conversion_algorithm(self):

        if self.project_type == 'pixel':
            if self.task == 'instance_segmentation':
                self.conversion_algorithm = sa_pixel_to_coco_instance_segmentation
            elif self.task == 'object_detection':
                self.conversion_algorithm = sa_pixel_to_coco_object_detection

        elif self.project_type == 'vector':
            if self.task == 'instance_segmentation':
                self.conversion_algorithm = sa_vector_to_coco_instance_segmentation
            elif self.task == 'object_detection':
                self.conversion_algorithm = sa_vector_to_coco_object_detection

    def __str__(self, ):
        return '{} object'.format(self.name)

    def _sa_to_coco_single(self, id_, json_path, id_generator):

        image_commons = self._prepare_single_image_commons(id_, json_path)
        annotations_per_image = []

        def make_annotation(
            category_id, image_id, bbox, segmentation, area, anno_id
        ):
            if self.task == 'object_detection':
                segmentation = [[bbox[0], bbox[1], bbox[0], bbox[1] + bbox[3], bbox[0] + bbox[2], bbox[1] + bbox[3], bbox[0] + bbox[2], bbox[1]]]
            annotation = {
                'id': anno_id,  # making sure ids are unique
                'image_id': image_id,
                'segmentation': segmentation,
                'iscrowd': 0,
                'bbox': bbox,
                'area': area,
                'category_id': category_id
            }

            return annotation

        res = self.conversion_algorithm(
            make_annotation, image_commons, id_generator
        )
        return res

    def sa_to_output_format(self):

        out_json = self._create_skeleton()
        out_json['categories'] = self._create_categories(
            os.path.join(self.export_root, 'classes_mapper.json')
        )
        jsons = self._load_sa_jsons()
        images = []
        annotations = []
        id_generator = self._make_id_generator()
        for id_, json_ in tqdm(enumerate(jsons)):
            try:
                res = self._sa_to_coco_single(id_, json_, id_generator)
            except Exception as e:
                raise
            images.append(res[0])
            if len(res[1])<1:
                self.increase_converted_count()
            for ann in res[1]:
                annotations.append(ann)
        out_json['annotations'] = annotations
        out_json['images'] = images

        json_data = json.dumps(out_json, indent=4)
        with open(
            os.path.join(self.output_dir, '{}.json'.format(self.dataset_name)),
            'w+'
        ) as coco_json:
            coco_json.write(json_data)
        print("NUMBER OF IMAGES FAILED TO CONVERT", self.failed_conversion_cnt)

        self.set_num_converted(len(jsons))

class KeypointDetectionStrategy(CoCoConverter):
    name = 'Keypoint Detection Converter'

    def __init__(self, dataset_name, export_root, project_type, output_dir):
        super().__init__(dataset_name, export_root, project_type, output_dir)
        self.__setup_conversion_algorithm()

    def __str__(self):
        return '{} object'.format(self.name)

    def __setup_conversion_algorithm(self):
        self.conversion_algorithm = sa_vector_to_coco_keypoint_detection

    def __make_image_info(self, json_path, id_, source_type):
        if source_type == 'pixel':
            rm_len = len('___pixel.json')
        elif source_type == 'vector':
            rm_len = len('___objects.json')

        image_path = json_path[:-rm_len]

        img_width, img_height = Image.open(image_path).size
        image_info = {
            'id': id_,
            'file_name': image_path[len('output') + 1:],
            'height': img_height,
            'width': img_width,
            'license': 1
        }

        return image_info

    def sa_to_output_format(self):
        out_json = self._create_skeleton()
        jsons = self._load_sa_jsons()

        images = []
        annotations = []

        id_generator = self._make_id_generator()
        id_generator_anno = self._make_id_generator()
        id_generator_img = self._make_id_generator()
        res = self.conversion_algorithm(
            jsons, id_generator, id_generator_anno, id_generator_img,
            self.__make_image_info
        )

        out_json['categories'] = res[0]
        out_json['annotations'] = res[1]
        out_json['images'] = res[2]
        json_data = json.dumps(out_json, indent=4)

        with open(
            os.path.join(self.output_dir, '{}.json'.format(self.dataset_name)),
            'w+'
        ) as coco_json:
            coco_json.write(json_data)

        self.set_num_converted(len(out_json['images']))
