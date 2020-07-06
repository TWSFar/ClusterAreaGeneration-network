"""
use rondom array replace objce witch was neglected
"""
import os
import cv2
import sys
import json
import h5py
import joblib
import argparse
import numpy as np
import os.path as osp
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString

import utils
from datasets import get_dataset
user_dir = osp.expanduser('~')


def parse_args():
    parser = argparse.ArgumentParser(description="convert to voc dataset")
    parser.add_argument('--dataset', type=str, default='Visdrone',
                        choices=['DOTA', 'Visdrone', 'TT100K', 'UAVDT'], help='dataset name')
    # parser.add_argument('--db_root', type=str,
    #                     default=user_dir+"/data/TT100K/",
    #                     # default="E:\\CV\\data\\visdrone",
    #                     help="dataset's root path")
    parser.add_argument('--imgsets', type=str, default=['train', 'test', 'val'],
                        nargs='+', help='for train or val')
    parser.add_argument('--aim', type=int, default=100,
                        help='gt aim scale in chip')
    parser.add_argument('--tiling', type=bool, default=True,
                        help='add tiling chip 3*2(just train)')
    parser.add_argument('--padding', type=str, default=['train', 'test'],
                        nargs='+', help='random padding neglect box')
    parser.add_argument('--show', type=bool, default=False,
                        help="show image and chip box")
    args = parser.parse_args()
    args.db_root = user_dir + f'/data/{args.dataset}/'
    return args


args = parse_args()
print(args)


class MakeDataset(object):
    def __init__(self):
        self.dataset = get_dataset(args.dataset, args.db_root)

        self.density_dir = self.dataset.density_voc_dir
        self.segmentation_dir = self.density_dir + '/SegmentationClass'

        self.dest_datadir = self.dataset.detect_voc_dir
        self.image_dir = self.dest_datadir + '/JPEGImages'
        self.anno_dir = self.dest_datadir + '/Annotations'
        self.list_dir = self.dest_datadir + '/ImageSets/Main'
        self.loc_dir = self.dest_datadir + '/Locations'
        self.gbm = joblib.load('/home/twsf/work/CRGNet/density_tools/weights/gbm_{}_{}.pkl'.format(args.dataset.lower(), args.aim))
        self._init_path()

    def _init_path(self):
        if not osp.exists(self.dest_datadir):
            os.makedirs(self.dest_datadir)
            os.makedirs(self.image_dir)
            os.makedirs(self.anno_dir)
            os.makedirs(self.list_dir)
            os.makedirs(self.loc_dir)

    def __call__(self):
        for imgset in args.imgsets:
            print("make {} detect dataset...".format(imgset))
            samples = self.dataset._load_samples(imgset)
            chip_ids = []
            chip_loc = dict()
            for i, sample in enumerate(samples):
                # if i > 3: break
                img_id = osp.splitext(osp.basename(sample['image']))[0]
                sys.stdout.write('\rcomplete: {:d}/{:d} {:s}'
                                 .format(i + 1, len(samples), img_id))
                sys.stdout.flush()

                loc = self.make_chip(sample, imgset)
                for i in range(len(loc)):
                    chip_ids.append('{}_{}'.format(img_id, i))
                chip_loc.update(loc)

            self.generate_imgset(chip_ids, imgset)

            # wirte chip loc json
            with open(osp.join(self.loc_dir, imgset+'_chip.json'), 'w') as f:
                json.dump(chip_loc, f)
                print('write loc json')

    def generate_region_gt(self, region_box, gt_bboxes, labels):
        chip_list = []
        for box in region_box:
            chip_list.append(np.array(box))

        # chip gt
        chip_gt_list = []
        chip_label_list = []
        chip_neglect_list = []
        if gt_bboxes is not None:
            for chip in chip_list:
                chip_gt = []
                chip_label = []
                neglect_gt = []
                for i, box in enumerate(gt_bboxes):
                    if utils.overlap(chip, box, 0.75):
                        box = [max(box[0], chip[0]), max(box[1], chip[1]),
                               min(box[2], chip[2]), min(box[3], chip[3])]
                        new_box = [box[0] - chip[0], box[1] - chip[1],
                                   box[2] - chip[0], box[3] - chip[1]]
                        chip_gt.append(np.array(new_box))
                        chip_label.append(labels[i])
                    elif utils.overlap(chip, box, 0.1):
                        box = [max(box[0], chip[0]), max(box[1], chip[1]),
                               min(box[2], chip[2]), min(box[3], chip[3])]
                        new_box = [box[0] - chip[0], box[1] - chip[1],
                                   box[2] - chip[0], box[3] - chip[1]]
                        neglect_gt.append(np.array(new_box, dtype=np.int))

                chip_gt_list.append(chip_gt)
                chip_label_list.append(chip_label)
                chip_neglect_list.append(neglect_gt)

        return chip_gt_list, chip_label_list, chip_neglect_list

    def generate_imgset(self, img_list, imgset):
        with open(osp.join(self.list_dir, imgset+'.txt'), 'w') as f:
            f.writelines([x + '\n' for x in img_list])
        print('\n%d images in %s set.' % (len(img_list), imgset))
        if imgset.lower() != 'val':
            op = 'a'
            if args.imgsets[0] == imgset:
                op = 'w'
            with open(osp.join(self.list_dir, 'traintest.txt'), op) as f:
                f.writelines([x + '\n' for x in img_list])
            print('\n%d images in traintest set.' % len(img_list))

    def make_xml(self, chip, bboxes, labels, image_name, chip_size):
        node_root = Element('annotation')

        node_folder = SubElement(node_root, 'folder')
        node_folder.text = args.dataset

        node_filename = SubElement(node_root, 'filename')
        node_filename.text = image_name

        node_object_num = SubElement(node_root, 'object_num')
        node_object_num.text = str(len(bboxes))

        node_location = SubElement(node_root, 'location')
        node_loc_xmin = SubElement(node_location, 'xmin')
        node_loc_xmin.text = str(int(chip[0]) + 1)
        node_loc_ymin = SubElement(node_location, 'ymin')
        node_loc_ymin.text = str(int(chip[1]) + 1)
        node_loc_xmax = SubElement(node_location, 'xmax')
        node_loc_xmax.text = str(int(chip[2]) + 1)
        node_loc_ymax = SubElement(node_location, 'ymax')
        node_loc_ymax.text = str(int(chip[3]) + 1)

        node_size = SubElement(node_root, 'size')
        node_width = SubElement(node_size, 'width')
        node_width.text = str(chip_size[0])
        node_height = SubElement(node_size, 'height')
        node_height.text = str(chip_size[1])
        node_depth = SubElement(node_size, 'depth')
        node_depth.text = '3'

        for i, bbox in enumerate(bboxes):
            node_object = SubElement(node_root, 'object')
            node_name = SubElement(node_object, 'name')
            node_name.text = str(labels[i])
            node_difficult = SubElement(node_object, 'difficult')
            node_difficult.text = '0'

            # voc dataset is 1-based
            node_bndbox = SubElement(node_object, 'bndbox')
            node_xmin = SubElement(node_bndbox, 'xmin')
            node_xmin.text = str(int(bbox[0]) + 1)
            node_ymin = SubElement(node_bndbox, 'ymin')
            node_ymin.text = str(int(bbox[1]) + 1)
            node_xmax = SubElement(node_bndbox, 'xmax')
            node_xmax.text = str(int(bbox[2] + 1))
            node_ymax = SubElement(node_bndbox, 'ymax')
            node_ymax.text = str(int(bbox[3] + 1))

        xml = tostring(node_root, encoding='utf-8')
        dom = parseString(xml)
        # print(xml)
        return dom

    def make_chip(self, sample, imgset):
        image = cv2.imread(sample['image'])
        height, width = sample['height'], sample['width']
        img_id = osp.splitext(osp.basename(sample['image']))[0]

        mask_path = osp.join(self.segmentation_dir, '{}.hdf5'.format(img_id))
        with h5py.File(mask_path, 'r') as hf:
            mask = np.array(hf['label'])
        mask_h, mask_w = mask.shape[:2]

        # make chip
        region_box, contours = utils.generate_box_from_mask(mask)

        region_box = utils.generate_crop_region(region_box, mask, (mask_w, mask_h), (width, height), self.gbm)

        region_box = utils.resize_box(region_box, (mask_w, mask_h), (width, height))

        if args.tiling and imgset != "val":
            tiling = utils.add_tiling((width, height))
            region_box = np.vstack((region_box, tiling))

        if args.show:
            utils.show_image(image, np.array(region_box))

        # if imgset == 'train':
        #     if len(region_box):
        #         region_box = np.vstack((region_box, np.array([0, 0, width, height])))
        #     else:
        #         region_box = np.array([[0, 0, width, height]])

        gt_bboxes, gt_cls, ignore = sample['bboxes'], sample['cls'], sample['ignore']

        chip_gt_list, chip_label_list, neglect_list = self.generate_region_gt(
            region_box, gt_bboxes, gt_cls)
        chip_loc = self.write_chip_and_anno(
            image, img_id, region_box, chip_gt_list, chip_label_list,
            ignore, neglect_list, imgset)

        return chip_loc

    def write_chip_and_anno(self, image, img_id,
                            chip_list, chip_gt_list,
                            chip_label_list, ignore, neglect_list, imgset):
        """write chips of one image to disk and make xml annotations
        """
        chip_loc = dict()
        chip_num = 0
        for box in ignore:
            ign_w, ign_h = box[2:] - box[:2]
            zeros_box = np.zeros(ign_h, ign_w, 3)
            image[box[1]:box[3], box[0]:box[2]] = zeros_box
        for i, chip in enumerate(chip_list):
            if len(chip_gt_list[i]) == 0:
                continue
            img_name = '{}_{}.jpg'.format(img_id, chip_num)
            xml_name = '{}_{}.xml'.format(img_id, chip_num)
            chip_loc[img_name] = [int(x) for x in chip]
            chip_size = (chip[2] - chip[0], chip[3] - chip[1])  # w, h
            chip_img = image[chip[1]:chip[3], chip[0]:chip[2], :].copy()
            assert len(chip_img.shape) == 3

            if imgset in args.padding and neglect_list is not None:
                for neg_box in neglect_list[i]:
                    neg_w = neg_box[2] - neg_box[0]
                    neg_h = neg_box[3] - neg_box[1]
                    zeros_box = np.zeros(neg_h, neg_w, 3)
                    chip_img[neg_box[1]:neg_box[3], neg_box[0]:neg_box[2], :] = zeros_box

            bbox = np.array(chip_gt_list[i], dtype=np.int)
            label = np.array(chip_label_list[i])

            dom = self.make_xml(chip, bbox, label, img_name, chip_size)
            with open(osp.join(self.anno_dir, xml_name), 'w') as f:
                f.write(dom.toprettyxml(indent='\t', encoding='utf-8').decode('utf-8')) 

            cv2.imwrite(osp.join(self.image_dir, img_name), chip_img)
            chip_num += 1

        return chip_loc


if __name__ == "__main__":
    makedataset = MakeDataset()
    makedataset()
