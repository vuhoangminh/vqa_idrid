import json
import sys
import os
import pandas as pd
import argparse
from collections import Counter, OrderedDict


def generate_image_id(index):
    image_id = str(index).zfill(5)
    return image_id


def create_questions(df, dataset, dir_interim, dataset_default="val"):
    filename = dir_interim + dataset + '_questions.json'
    dataset = dataset_default

    if os.path.exists(filename):
        print('>> loading', filename)
        with open(filename) as f:
            dataset_questions = json.load(f)

    else:
        dataset_questions = []
        for index, row in df.iterrows():
            if index == 0:
                temp_dataset_questions_annotations = []
            if row['dataset'] == dataset:
                question_id = str(row['question_id']).zfill(12)
                image_name = row['file_id']
                question = row['question']

                row_dict = OrderedDict()
                row_dict['question_id'] = question_id
                row_dict['image_name'] = image_name
                row_dict['question'] = question

                temp_dataset_questions_annotations = temp_dataset_questions_annotations + \
                    [row_dict]

            if index % 1000 == 0 and index > 0:
                sys.stdout.write("processing %d/%d (%.2f%% done)   \r" %
                                 (index, len(df), index*100.0/len(df)))
                sys.stdout.flush()
                dataset_questions = dataset_questions + \
                    temp_dataset_questions_annotations
                temp_dataset_questions_annotations = []

        dataset_questions = dataset_questions + \
            temp_dataset_questions_annotations
        json_data = dataset_questions

        with open(filename, 'w') as fp:
            print('>> saving', filename)
            json.dump(json_data, fp)

    return dataset_questions


def create_questions_annotations(df, dataset, dir_interim):
    filename = dir_interim + dataset + '_questions_annotations.json'
    if dataset in ["trainval", "trainval_augment"]:
        dataset = ["train", "val"]
    elif dataset == "train_augment":
        dataset = "train"
    elif dataset == "val_augment":
        dataset = "val"        
    elif dataset == "test_augment":
        dataset = "test"        
    else:
        dataset = [dataset]

    if os.path.exists(filename):
        print('>> loading', filename)
        with open(filename) as f:
            dataset_questions_annotations = json.load(f)

    else:
        dataset_questions_annotations = []
        for index, row in df.iterrows():
            if index == 0:
                temp_dataset_questions_annotations = []

            if row['dataset'] in dataset:
                question_id = str(row['question_id']).zfill(12)
                image_name = row['file_id']
                question = row['question']
                answer = row['answer']
                answers_occurence = [[answer, 10]]

                row_dict = OrderedDict()
                row_dict['question_id'] = question_id
                row_dict['image_name'] = image_name
                row_dict['question'] = question
                row_dict['answer'] = answer
                row_dict['answers_occurence'] = answers_occurence

                temp_dataset_questions_annotations = temp_dataset_questions_annotations + \
                    [row_dict]

            if index % 1000 == 0 and index > 0:
                sys.stdout.write("processing %d/%d (%.2f%% done)   \r" %
                                 (index, len(df), index*100.0/len(df)))
                sys.stdout.flush()
                dataset_questions_annotations = dataset_questions_annotations + \
                    temp_dataset_questions_annotations
                temp_dataset_questions_annotations = []

        dataset_questions_annotations = dataset_questions_annotations + \
            temp_dataset_questions_annotations
        json_data = dataset_questions_annotations

        with open(filename, 'w+') as fp:
            print('>> saving', filename)
            json.dump(json_data, fp)

    return dataset_questions_annotations


def create_full_imageid_quesid_questype(df, dir_interim):
    cols = ['file_id', 'image_id', 'question', 'question_id',
            'question_type', 'answer', 'multiple_choice_answer',
            'answer', 'answer_confidence', 'answer_id',
            'dataset']
    full_df = pd.DataFrame(columns=cols)
    question_list = find_question_list(df)
    for index, row in df.iterrows():
        # print("processing {}/{}".format(index+1, len(df)))
        if index % 10 == 0:
            sys.stdout.write("processing %d/%d (%.2f%% done)   \r" %
                             (index, len(df), index*100.0/len(df)))
            sys.stdout.flush()
        file_id = row['file_id']
        dataset = row['dataset']
        if 'image_id' in list(df):
            image_id = row['image_id']
        else:
            image_id = generate_image_id(index)
        question_i = 0
        temp_df = pd.DataFrame(columns=cols)
        for question in question_list:
            try:
                image_id = str(image_id)
            except ValueError:
                pass
            question_id = str(image_id + str(question_i).zfill(6)).zfill(12)
            answer = row[question]
            row_df = pd.DataFrame({'file_id': [file_id],
                                   'image_id': [image_id],
                                   'question': [question],
                                   'question_id': [question_id],
                                   'question_type': ['is the'],
                                   'answer': [answer],
                                   'multiple_choice_answer': [answer],
                                   'answer_confidence': ['yes'],
                                   'answer_id': [1],
                                   'dataset': [dataset]
                                   })
            if len(temp_df) == 0:
                temp_df = row_df
            else:
                temp_df = temp_df.append(row_df)
            question_i = question_i + 1
        if len(full_df) == 0:
            full_df = temp_df
        else:
            full_df = full_df.append(temp_df)
    return full_df


def find_question_list(df):
    is_removed = ["file_id", "image_id", "dataset"]
    temp = list(df)
    cols = [k for k in temp if k not in is_removed]
    return cols


def insert_dataset_to_df(df, segmentation_dict_tool, is_split=True):
    list_train = segmentation_dict_tool["train"]
    list_val = segmentation_dict_tool["val"]
    temp_df = df
    temp_df['dataset'] = 'image'
    for index, row in temp_df.iterrows():
        file_id = row["file_id"]
        if is_split:
            file_id = file_id.split('.')[0]
        if file_id in list_train:
            temp_df["dataset"][index] = "train"
        if file_id in list_val:
            temp_df["dataset"][index] = "val"
    return temp_df
