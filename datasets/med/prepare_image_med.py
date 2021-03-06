import os
import datasets.utils.print_utils as print_utils
import datasets.utils.paths_utils as path_utils
import datasets.utils.image_utils as image_utils
import datasets.utils.io_utils as io_utils
import datasets.med.preprocess as preprocess
from PIL import Image
import numpy as np
import pandas as pd
import glob
import shutil
import random
import cv2
from tqdm import tqdm
import PIL.ImageEnhance as ie
random.seed(1988)


CURRENT_WORKING_DIR = os.path.realpath(__file__)
PROJECT_DIR = path_utils.get_project_dir(CURRENT_WORKING_DIR, "vqa_idrid")
DATASETS_TRAIN_DIR = PROJECT_DIR + \
    "/data/raw/vqa_med/ImageClef-2019-VQA-Med-Training/Train_images/"
DATASETS_VALID_DIR = PROJECT_DIR + \
    "/data/raw/vqa_med/ImageClef-2019-VQA-Med-Validation/Val_images/"
DATASETS_TEST_DIR = PROJECT_DIR + \
    "/data/raw/vqa_med/VQAMed2019Test/VQAMed2019_Test_Images/"
QA_TRAIN_TXT = PROJECT_DIR + \
    "/data/raw/vqa_med/ImageClef-2019-VQA-Med-Training/All_QA_Pairs_train.txt"
QA_VALID_TXT = PROJECT_DIR + \
    "/data/raw/vqa_med/ImageClef-2019-VQA-Med-Validation/All_QA_Pairs_val.txt"
PREPROCESSED_DIR = PROJECT_DIR + \
    "/data/raw/vqa_med/preprocessed/"
CLASSIFICATION_DIR = PROJECT_DIR + \
    "/data/raw/vqa_med/preprocessed/classification"
RAW_DIR = PROJECT_DIR + "/data/vqa_med/raw/raw/"
PROCESSED_QA_PER_QUESTION_PATH = RAW_DIR + "google_keywords.csv"


LIST_PLANE = {
    "axial": "axial",
    "sagittal": "sagittal",
    "coronal": "coronal",
    "ap": "ap",
    "lateral": "lateral",
    "frontal": "frontal",
    "pa": "pa",
    "transverse": "transverse",
    "oblique": "oblique",
    "longitudinal": "longitudinal",
    "decubitus": "decubitus",
    "3d reconstruction": "reconstruction",
    "mammo - mlo": "mlo",
    "mammo - cc": "cc",
    "mammo - mag cc": "mag",
    "mammo - xcc": "xcc",
}

LIST_ORGAN = {
    "breast": "breast",
    "skull and contents": "skull",
    "face, sinuses, and neck": "face",
    "spine and contents": "spine",
    "musculoskeletal": "musculoskeletal",
    "heart and great vessels": "heart",
    "lung, mediastinum, pleura": "lung",
    "gastrointestinal": "gastrointestinal",
    "genitourinary": "genitourinary",
    "vascular and lymphatic": "vascular",
}

LIST_MODALITY = {
    "xr - plain film": "xr_plain",
    "ct - noncontrast": "ct_noncontrast",
    "ct w/contrast (iv)": "ct_wcontrast",
    "ct - gi & iv contrast": "ct_giiv",
    "cta - ct angiography": "cta",
    "ct - gi contrast": "ct_gi",
    "ct - myelogram": "ct_myelogram",
    "tomography": "tomography",
    "mr - t1w w/gadolinium": "mr_t1w_wgadolinium",
    "mr - t1w - noncontrast": "mr_t1w_noncontrast",
    "mr - t2 weighted": "mr_t2_weighted",
    "mr - flair": "mr_flair",
    "mr - t1w w/gd (fat suppressed)": "mr_t1w_wfat",
    "mr t2* gradient,gre,mpgr,swan,swi": "mr_t2_mpgr",
    "mr - dwi diffusion weighted": "mr_dwi",
    "mra - mr angiography/venography": "mra_mr_angiography",
    "mr - other pulse seq.": "mr_other",
    "mr - adc map (app diff coeff)": "mr_adc",
    "mr - pdw proton density": "mr_pdw",
    "mr - stir": "mr_stir",
    "mr - fiesta": "mr_fiesta",
    "mr - flair w/gd": "mr_flair_wgd",
    "mr - t1w spgr": "mr_t1w_spgr",
    "mr - t2 flair w/contrast": "mr_t2_flair",
    "mr t2* gradient gre": "mr_t2_gradientgre",
    "us - ultrasound": "us",
    "us-d - doppler ultrasound": "usd",
    "mammograph": "mammograph",
    "bas - barium swallow": "bas",
    "ugi - upper gi": "ugi",
    "be - barium enema": "be",
    "sbft - small bowel": "sbft",
    "an - angiogram": "angiogram",
    "venogram": "venogram",
    "nm - nuclear medicine": "nm",
    "pet - positron emission": "pet",
}


LIST_AUGMENT = [
    "fliplr",
    "rot10",
    "rot20",
    "rot30",
    "rot_10",
    "rot_20",
    "rot_30",
    # "bright1",
    # "bright_1",
    "sharp3",
    "sharp_3",
]


def get_class_image_model(df, line, is_keyword=False):
    line = line.split("|")
    image, question, answer = line[0], line[1], line[2].split("\n")[0]

    plane_keys = list(LIST_PLANE.keys())
    organ_keys = list(LIST_ORGAN.keys())
    modality_keys = list(LIST_MODALITY.keys())

    modality, plane, organ, abnormal = " ", " ", " ", " "

    is_found = False
    for key in plane_keys:
        if key in answer and "plane" in question:
            is_found = True
            if is_keyword:
                plane = key
            else:
                plane = LIST_PLANE[key]
    for key in organ_keys:
        if key in answer and ("organ" in question or "part of the body" in question):
            is_found = True
            if is_keyword:
                organ = key
            else:
                organ = LIST_ORGAN[key]
    for key in modality_keys:
        if key in answer:
            is_found = True
            if is_keyword:
                modality = key
            else:
                modality = LIST_MODALITY[key]

    if not is_found:
        abnormal = answer

    index = df.index[df['image'] == image].tolist()

    if plane != " ":
        if len(index) == 0:
            df = df.append(pd.DataFrame({"image": [image],
                                         "plane": [plane]}),
                           ignore_index=True)
        else:
            df.at[index[0], 'plane'] = plane
    if organ != " ":
        if len(index) == 0:
            df = df.append(pd.DataFrame({"image": [image],
                                         "organ": [organ]}),
                           ignore_index=True)
        else:
            df.at[index[0], 'organ'] = organ
    if modality != " ":
        if len(index) == 0:
            df = df.append(pd.DataFrame({"image": [image],
                                         "modality": [modality]}),
                           ignore_index=True)
        else:
            df.at[index[0], 'modality'] = modality
    if abnormal not in [" ", "yes", "no"]:
        if len(index) == 0:
            df = df.append(pd.DataFrame({"image": [image],
                                         "abnormal": [abnormal]}),
                           ignore_index=True)
        else:
            df.at[index[0], 'abnormal'] = abnormal
    return df


def move_to_corresponding_label_classification():
    dataset_dir = QA_TRAIN_TXT

    with open(dataset_dir) as f:
        lines = f.readlines()

    df = pd.DataFrame(columns=['image', 'modality', 'plane', 'organ'])
    for index in tqdm(range(len(lines))):
        line = lines[index]
        df = get_class_image_model(df, line)

    print(df)

    n_group = len(set(zip(df['plane'], df['organ'], df['modality'])))
    print(n_group)

    df['label'] = df.plane.map(str) + "_" + df.organ.map(str)

    for index, row in df.iterrows():
        image = row["image"]
        if image == "synpic47258":
            a = 2
        label = row["label"]
        label_dir = os.path.join(CLASSIFICATION_DIR, label)
        path_utils.make_dir(label_dir)
        in_path = os.path.join(PREPROCESSED_DIR, "train",
                               "{}.jpg".format(image))
        out_path = os.path.join(label_dir, "{}.jpg".format(image))
        shutil.copy(in_path, out_path)


def preprocess_dataset(dataset="train", is_show=False, is_overwrite=False, is_augment=False):
    if dataset == "train":
        dataset_dir = DATASETS_TRAIN_DIR
    elif dataset == "val":
        dataset_dir = DATASETS_VALID_DIR
    else:
        dataset_dir = DATASETS_TEST_DIR

    if is_augment:
        preprocessed_dir = os.path.join(
            PREPROCESSED_DIR, "raw", dataset + "_augment")
    else:
        preprocessed_dir = os.path.join(PREPROCESSED_DIR, "raw", dataset)

    if is_overwrite or not os.path.exists(preprocessed_dir):
        path_utils.make_dir(preprocessed_dir)
        img_paths = glob.glob(os.path.join(dataset_dir, "*.jpg"))

        for index in tqdm(range(len(img_paths))):
            img_preprocessed = preprocess.process(index, img_paths)
            img_preprocessed = cv2.resize(img_preprocessed, (256, 256))
            if is_show:
                cv2.imshow('Done', img_preprocessed)
                cv2.waitKey(0)
            out_path = os.path.join(
                preprocessed_dir, path_utils.get_filename(img_paths[index]))
            cv2.imwrite(out_path, img_preprocessed)
            out = img_preprocessed

            if is_augment:
                for augment in LIST_AUGMENT:
                    out_path = os.path.join(
                        preprocessed_dir, path_utils.get_filename_without_extension(img_paths[index]) + "_{}.jpg".format(augment))
                    img_preprocessed = Image.fromarray(out)
                    if augment == "fliplr":
                        img_preprocessed = img_preprocessed.transpose(
                            Image.FLIP_LEFT_RIGHT)
                    elif augment == "rot10":
                        img_preprocessed = img_preprocessed.rotate(10)
                    elif augment == "rot20":
                        img_preprocessed = img_preprocessed.rotate(20)
                    elif augment == "rot30":
                        img_preprocessed = img_preprocessed.rotate(30)
                    elif augment == "rot_10":
                        img_preprocessed = img_preprocessed.rotate(-10)
                    elif augment == "rot_20":
                        img_preprocessed = img_preprocessed.rotate(-20)
                    elif augment == "rot_30":
                        img_preprocessed = img_preprocessed.rotate(-30)
                    elif augment == "bright1":
                        img_preprocessed = ie.Contrast(
                            img_preprocessed).enhance(1)
                    elif augment == "bright_1":
                        img_preprocessed = ie.Contrast(
                            img_preprocessed).enhance(-1)
                    elif augment == "sharp3":
                        img_preprocessed = ie.Sharpness(
                            img_preprocessed).enhance(3)
                    elif augment == "sharp_3":
                        img_preprocessed = ie.Sharpness(
                            img_preprocessed).enhance(-3)
                    # elif augment == "contrast2":
                    #     img_preprocessed = ie.Contrast(img_preprocessed).enhance(2)
                    # elif augment == "contrast_2":
                    #     img_preprocessed = ie.Contrast(img_preprocessed).enhance(-2)
                    img_preprocessed.save(out_path)


def analyze_train_val():
    dataset_dir = QA_VALID_TXT
    with open(dataset_dir, encoding='UTF-8') as f:
        lines = f.readlines()

    df = pd.DataFrame(columns=['image', 'modality',
                               'plane', 'organ', 'abnormal'])

    for index in tqdm(range(len(lines))):
        line = lines[index]
        df = get_class_image_model(df, line, is_keyword=True)

    df = df.replace(np.nan, ' ', regex=True)
    print(df)

    dataset_dir = QA_TRAIN_TXT

    with open(dataset_dir, encoding='UTF-8') as f:
        lines = f.readlines()

    for index in tqdm(range(len(lines))):
        line = lines[index]
        df = get_class_image_model(df, line, is_keyword=True)
    df = df.replace(np.nan, ' ', regex=True)

    print(df)

    n_group = len(set(zip(df['plane'], df['organ'], df['modality'])))
    print(n_group)

    df['search'] = df.plane.map(str) + " + " + df.organ.map(str) + \
        " + " + df.modality.map(str) + " + " + df.abnormal.map(str)

    df.to_csv(PROCESSED_QA_PER_QUESTION_PATH, index=False)


def main(overwrite=False):
    # for dataset in ["train", "val", "test"]:
    #     preprocess_dataset(dataset=dataset, is_show=False)
    #     preprocess_dataset(dataset=dataset, is_show=False,
    #                        is_augment=True, is_overwrite=False)

    # move_to_corresponding_label_classification()

    analyze_train_val()


if __name__ == "__main__":
    main(overwrite=False)
