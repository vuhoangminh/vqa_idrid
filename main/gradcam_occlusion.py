import torch._utils
import yaml
import vqa.lib.utils as utils
import vqa.datasets as datasets
import vqa.models as models_vqa
import datasets.utils.paths_utils as paths_utils
import datasets.utils.print_utils as print_utils
import argparse
from random import shuffle
import glob
import pandas as pd
import torch
import cv2
import numpy as np
import string
from torch.nn import functional as F
from torch.autograd import Variable
import torchvision.transforms as transforms
from PIL import Image
import PIL
import os
import vqa.models.convnets_idrid as convnets_idrid
import vqa.models.convnets_breast as convnets_breast
import vqa.models.convnets_tools as convnets_tools
import vqa.models.convnets as convnets
from vqa.datasets.vqa_processed import tokenize_mcb

CURRENT_WORKING_DIR = os.path.realpath(__file__)
PROJECT_DIR = paths_utils.get_project_dir(CURRENT_WORKING_DIR, "vqa_idrid")
BREAST_PROCESSED_QA_PER_QUESTION_PATH = PROJECT_DIR + \
    "/data/vqa_breast/raw/raw/" + "breast_qa_per_question.csv"
IDRID_PROCESSED_QA_PER_QUESTION_PATH = PROJECT_DIR + \
    "/data/vqa_idrid/raw/raw/" + "idrid_qa_per_question.csv"
TOOLS_PROCESSED_QA_PER_QUESTION_PATH = PROJECT_DIR + \
    "/data/vqa_tools/raw/raw/" + "tools_qa_per_question.csv"


parser = argparse.ArgumentParser(
    description='Demo server',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--vqa_model', type=str,
                    default='minhmul_noatt_train_2048')
parser.add_argument('--dir_logs', type=str,
                    default='logs/breast/minhmul_noatt_train_2048',
                    help='dir logs')
parser.add_argument('--path_opt', type=str,
                    # default='logs/vqa2/blocmutan_noatt_fbresnet152torchported_save_all/blocmutan_noatt.yaml',
                    default='logs/breast/minhmul_noatt_train_2048/minhmul_noatt_train_2048.yaml',
                    help='path to a yaml options file')
parser.add_argument('--resume', type=str,
                    default='best',
                    help='path to latest checkpoint')
parser.add_argument('--cuda', type=bool,
                    const=True,
                    nargs='?',
                    default=True,
                    help='path to latest checkpoint')
parser.add_argument('--vqa_trainsplit', type=str,
                    choices=['train', 'trainval'], default="train")
parser.add_argument('--st_type',
                    help='skipthoughts type')
parser.add_argument('--st_dropout', type=float)
parser.add_argument('--st_fixed_emb', default=None, type=utils.str2bool,
                    help='backprop on embedding')
# model options
parser.add_argument('--arch', choices=models_vqa.model_names,
                    help='vqa model architecture: ' +
                    ' | '.join(models_vqa.model_names))


try:
    torch._utils._rebuild_tensor_v2
except AttributeError:
    def _rebuild_tensor_v2(storage, storage_offset, size, stride, requires_grad, backward_hooks):
        tensor = torch._utils._rebuild_tensor(
            storage, storage_offset, size, stride)
        tensor.requires_grad = requires_grad
        tensor._backward_hooks = backward_hooks
        return tensor
    torch._utils._rebuild_tensor_v2 = _rebuild_tensor_v2


def process_visual(img, cnn, vqa_model="minhmul_noatt_train_2048"):
    normalize = transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        normalize
    ])

    if len(img.shape) == 3:
        visual_PIL = Image.fromarray(img)
        visual_tensor = transform(visual_PIL)
        visual_data = torch.FloatTensor(1, 3, 224, 224)
        visual_data[0][0] = visual_tensor[0]
        visual_data[0][1] = visual_tensor[1]
        visual_data[0][2] = visual_tensor[2]
    else:
        visual_data = torch.FloatTensor(img.shape[0], 3, 224, 224)
        for i in range(img.shape[0]):
            visual_PIL = Image.fromarray(np.asarray(img[i, :, :, :], np.uint8))
            visual_tensor = transform(visual_PIL)
            visual_data[i][0] = visual_tensor[0]
            visual_data[i][1] = visual_tensor[1]
            visual_data[i][2] = visual_tensor[2]

    # print('visual', visual_data.size(), visual_data.mean())

    visual_data = visual_data.cuda()
    visual_input = Variable(visual_data)

    visual_features = cnn(visual_input)
    if 'noatt' in vqa_model:
        nb_regions = visual_features.size(2) * visual_features.size(3)
        visual_features = visual_features.sum(
            3).sum(2).div(nb_regions).view(-1, 2048)
    return visual_features


def process_question(args, question_str, trainset):
    question_tokens = tokenize_mcb(question_str)
    question_data = torch.LongTensor(1, len(question_tokens))
    for i, word in enumerate(question_tokens):
        if word in trainset.word_to_wid:
            question_data[0][i] = trainset.word_to_wid[word]
        else:
            question_data[0][i] = trainset.word_to_wid['UNK']
    if args.cuda:
        question_data = question_data.cuda()
    question_input = Variable(question_data)
    # print('question', question_str, question_tokens, question_data)

    return question_input


def process_answer(answer_var, trainset, model, dataset):
    list_answer = []
    for i in range(answer_var.shape[0]):
        answer_sm = torch.nn.functional.softmax(
            Variable(answer_var.data[i].cpu()))

        if dataset == "idrid":
            topk = 3
        else:
            topk = 5

        max_, aid = answer_sm.topk(topk, 0, True, True)

        ans = []
        val = []
        for i in range(topk):
            ans.append(trainset.aid_to_ans[aid.data[i]])
            val.append(max_.data[i])
        answer = {'ans': ans, 'val': val}

        list_answer.append(answer)

    return list_answer, answer_sm


def load_dict_torch_031(model, path_ckpt):
    model_dict = torch.load(path_ckpt)
    model_dict_clone = model_dict.copy()  # We can't mutate while iterating
    for key, value in model_dict_clone.items():
        if key.endswith(('running_mean', 'running_var')):
            del model_dict[key]
    model.load_state_dict(model_dict, False)
    return model


def load_vqa_model(args, dataset, vqa_model="minhmul_noatt_train_2048"):
    path = "options/{}/{}.yaml".format(dataset, vqa_model)
    args = parser.parse_args()
    options = {
        'vqa': {
            'trainsplit': args.vqa_trainsplit
        },
        'logs': {
            'dir_logs': args.dir_logs
        },
        'model': {
            'arch': args.arch,
            'seq2vec': {
                'type': args.st_type,
                'dropout': args.st_dropout,
                'fixed_emb': args.st_fixed_emb
            }
        }
    }
    with open(path, 'r') as handle:
        options_yaml = yaml.load(handle)
    options = utils.update_values(options, options_yaml)
    if 'vgenome' not in options:
        options['vgenome'] = None

    trainset = datasets.factory_VQA(options['vqa']['trainsplit'],
                                    options['vqa'],
                                    options['coco'],
                                    options['vgenome'])

    model = models_vqa.factory(options['model'],
                               trainset.vocab_words(), trainset.vocab_answers(),
                               cuda=False, data_parallel=False)

    # load checkpoint
    path_ckpt_model = "logs/{}/{}/best_model.pth.tar".format(
        dataset, vqa_model)
    if os.path.isfile(path_ckpt_model):
        model = load_dict_torch_031(model, path_ckpt_model)
    return model


def show_cam_on_image(img, mask):
    heatmap = cv2.applyColorMap(np.uint8(255*mask), cv2.COLORMAP_JET)
    # heatmap = np.float32(heatmap) / 255
    # cam = heatmap + np.float32(img)
    result = heatmap * 0.5 + img * 0.5
    # cam = cam / np.max(cam)
    return result


def get_gadcam_image(feature_conv, weight_softmax, class_idx):
    # generate the class activation maps upsample to 256x256
    size_upsample = (256, 256)
    bz, nc, h, w = feature_conv.shape
    for idx in class_idx:
        cam = weight_softmax[idx].dot(feature_conv.reshape((nc, h*w)))
        cam = cam.reshape(h, w)

        cam = np.maximum(cam, 0)
        cam = cv2.resize(cam, size_upsample)
        cam = cam - np.min(cam)
        cam = cam / np.max(cam)
    return cam


def get_gradcam_from_image_model(path_img, cnn, dataset, finalconv_name="layer4"):

    cnn.eval()

    # hook the feature extractor
    features_blobs = []

    def hook_feature(module, input, output):
        features_blobs.append(output.data.cpu().numpy())

    cnn._modules.get(finalconv_name).register_forward_hook(hook_feature)

    # get the softmax weight
    params = list(cnn.parameters())
    weight_softmax = np.squeeze(params[-2].data.cpu().numpy())

    normalize = transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )
    preprocess = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        normalize
    ])

    img_name = paths_utils.get_filename_without_extension(path_img)
    img_pil = Image.open(path_img)

    img_tensor = preprocess(img_pil)
    img_variable = Variable(img_tensor.unsqueeze(0))
    img_variable = img_variable.cuda()
    logit = cnn(img_variable)

    paths_utils.make_dir("temp/gradcam/{}/".format(dataset))
    in_path = "temp/gradcam/{}/{}_in.jpg".format(dataset, img_name)

    # img_pil.thumbnail((256, 256), Image.ANTIALIAS)
    img_pil = img_pil.resize((256, 256), resample=PIL.Image.NEAREST)
    img_pil.save(in_path)

    # download the imagenet category list
    classes = {
        0: "Benign",
        1: "InSitu",
        2: "Invasive",
        3: "Normal"
    }

    h_x = F.softmax(logit, dim=1).data.squeeze()
    probs, idx = h_x.sort(0, True)
    probs = probs.cpu().numpy()
    idx = idx.cpu().numpy()

    # generate class activation mapping for the top1 prediction
    cam = get_gadcam_image(features_blobs[0], weight_softmax, [idx[0]])

    img_name = paths_utils.get_filename_without_extension(path_img)

    img = cv2.imread(in_path)

    result = show_cam_on_image(img, cam)

    out_path = "temp/gradcam/{}/{}_cnn.jpg".format(dataset,
                                                   img_name)

    cv2.imwrite(out_path, result)

    return result, out_path, features_blobs


def get_gadcam_vqa(feature_conv, weight_softmax, weight_softmax_b, class_idx):
    # generate the class activation maps upsample to 256x256
    size_upsample = (256, 256)
    bz, nc, h, w = feature_conv.shape
    for idx in class_idx:
        cam = weight_softmax[idx].dot(feature_conv.reshape((nc, h*w)))
        cam = cam.reshape(h, w)

        cam = np.maximum(cam, 0)
        cam = cv2.resize(cam, size_upsample)
        cam = cam - np.min(cam)
        cam = cam / np.max(cam)
    return cam


def initialize(args, dataset="breast"):
    options = {
        'logs': {
            'dir_logs': args.dir_logs
        }
    }
    if args.path_opt is not None:
        with open(args.path_opt, 'r') as handle:
            options_yaml = yaml.load(handle)
        options = utils.update_values(options, options_yaml)

    print("\n>> load trainset...")
    trainset = datasets.factory_VQA(options['vqa']['trainsplit'],
                                    options['vqa'],
                                    options['coco'],
                                    options['vgenome'])

    print("\n>> load cnn model...")
    if dataset == "idrid":
        cnn = convnets_idrid.factory(
            {'arch': "resnet152_idrid"}, cuda=True, data_parallel=False)
    elif dataset == "tools":
        cnn = convnets_tools.factory(
            {'arch': "resnet152_tools"}, cuda=True, data_parallel=False)
    elif dataset == "breast":
        cnn = convnets_breast.factory(
            {'arch': "resnet152_breast"}, cuda=True, data_parallel=False)
    elif dataset == "vqa2":
        cnn = convnets.factory(
            {'arch': "fbresnet152"}, cuda=True, data_parallel=False)

    cnn = cnn.cuda()

    print("\n>> load vqa model...")
    model = load_vqa_model(args, dataset, args.vqa_model)
    model = model.cuda()

    return cnn, model, trainset


def process_one_batch_of_occlusion(args, cnn, model, trainset, visual_PIL, question_str, list_box, dataset="breast", is_print=True):
    visual_PIL = visual_PIL.resize((256, 256))

    if list_box is not None:
        img = np.zeros(
            (len(list_box), visual_PIL.size[0], visual_PIL.size[1], 3))
        for i in range(len(list_box)):
            box = list_box[i]
            im = np.array(visual_PIL)
            # im = np.moveaxis(im, -1, 0)
            im[box[0]:box[1], box[2]:box[3], :] = 0
            img[i, :, :, :] = im
    else:
        img = np.zeros((32, visual_PIL.size[0], visual_PIL.size[1], 3))
        for i in range(32):
            img[i, :, :, :] = np.array(visual_PIL)

    if is_print:
        print("\n>> extract visual features...")
    visual_features = process_visual(img, cnn, args.vqa_model)

    if is_print:
        print("\n>> extract question features...")
    question_features_one = process_question(args, question_str, trainset)
    question_features = torch.LongTensor(
        visual_features.shape[0], question_features_one.shape[1])
    for i in range(visual_features.shape[0]):
        question_features[i] = question_features_one[0]
    question_features = question_features.cuda()

    # if visual_features.shape[0] == 1:
    #     v = torch.FloatTensor(2, 2048, 7, 7)
    #     q = torch.LongTensor(2, 6)

    #     for i in range(2):
    #         v[i] = visual_features[0]
    #         q[i] = q[0]
    #     visual_features = v.cuda()
    #     question_features = q.cuda()

    if is_print:
        print("\n>> get answers...")
    answer, _ = process_answer(
        model(visual_features, question_features)[0], trainset, model, dataset)

    return answer


def update_args(args, vqa_model="minhmul_noatt_train_2048", dataset="breast"):
    args.vqa_model = vqa_model
    args.dir_logs = "logs/{}/{}".format(dataset, vqa_model)
    args.path_opt = "logs/{}/{}/{}.yaml".format(dataset, vqa_model, vqa_model)
    return args


def get_path(project_dir, dataset="breast"):
    path_dir = project_dir
    path = os.path.join(path_dir, "temp/test_{}/".format(dataset))
    return path


def save_image(image, mask, occurrence,
               out_color_path,
               out_gray_path,
               out_avg_path, is_show=False):
    mask = mask - np.min(mask)
    mask = mask/np.max(mask)

    occurrence = mask/occurrence

    heatmap = cv2.applyColorMap(np.uint8(255*mask), cv2.COLORMAP_JET)

    image = image.resize(((256, 256)))
    result = heatmap * 0.5 + np.array(image) * 0.5

    mask = Image.fromarray((mask * 255).astype(np.uint8))
    result = Image.fromarray(result.astype(np.uint8))
    occurrence = Image.fromarray((occurrence * 255).astype(np.uint8))

    if is_show:
        mask.show()
        image.show()
        result.show()
        occurrence.show()

    result.save(out_color_path)
    # mask.save(out_gray_path)
    # occurrence.save(out_avg_path)


def get_answer(dataset, image_path, question):
    QA_PER_QUESTION_PATH = PROJECT_DIR + \
        "/data/vqa_{}/raw/raw/{}_qa_per_question.csv".format(dataset, dataset)
    df = pd.read_csv(QA_PER_QUESTION_PATH)
    image_name = paths_utils.get_filename(image_path)
    list_file_id = df.index[df['file_id'] == image_name].tolist()
    list_question = df.index[df['question'].str.replace(
        '[^\w\s]', '').str.lower() == question.translate(string.punctuation)].tolist()
    try:
        index = list(set(list_file_id).intersection(list_question))[0]
        answer = df.at[index, "answer"]
    except:
        answer = None
    return answer


def process_occlusion(path, dataset="breast"):
    # global args
    args = parser.parse_args()

    LIST_QUESTION_BREAST = [
        "how many classes are there",
        "is there any benign class in the image",
        "is there any in situ class in the image",
        "is there any invasive class in the image",
        "what is the major class in the image",
        "what is the minor class in the image",
        "is benign in 64_64_32_32 location",
        "is invasive in 96_96_32_32 location",
    ]

    LIST_QUESTION_TOOLS = [
        "how many tools are there",
        "is scissors in 64_32_32_32 location",
        "is irrigator in 64_96_32_32 location",
        "is grasper in 64_96_32_32 location"
        "is bipolar in 64_96_32_32 location"
        "is hook in 64_96_32_32 location"
        "is clipper in 64_96_32_32 location"
        "is specimenbag in 64_96_32_32 location"
        "is there any grasper in the image",
        "is there any bipolar in the image",
        "is there any hook in the image",
        "is there any scissors in the image",
        "is there any clipper in the image",
        "is there any irrigator in the image",
        "is there any specimenbag in the image",
    ]

    LIST_QUESTION_IDRID = [
        "is there haemorrhages in the fundus",
        "is there microaneurysms in the fundus",
        "is there soft exudates in the fundus",
        "is there hard exudates in the fundus",
        "is hard exudates larger than soft exudates",
        "is haemorrhages smaller than microaneurysms",
        "is there haemorrhages in the region 32_32_16_16",
        "is there microaneurysms in the region 96_96_16_16",
    ]

    LIST_QUESTION_VQA2 = [
        "what color is the hydrant",
        "why are the men jumping to catch",
        "is the water still",
        "how many people are in the image"
    ]

    if dataset == "breast":
        list_question = LIST_QUESTION_BREAST
    elif dataset == "tools":
        list_question = LIST_QUESTION_TOOLS
    elif dataset == "idrid":
        list_question = LIST_QUESTION_IDRID
    elif dataset == "vqa2":
        list_question = LIST_QUESTION_VQA2

    img_dirs = glob.glob(os.path.join(path, "*"))

    # args = update_args(
    #     args, vqa_model="minhmul_att_train_2048", dataset=dataset)
    args = update_args(
        args, vqa_model="minhmul_att_train", dataset=dataset)

    shuffle(img_dirs)
    shuffle(list_question)
    # for (path_img, question_str) in zip(img_dirs, list_question):
    for path_img in img_dirs:
        for question_str in list_question:
            if dataset in ["vqa", "vqa2"]:
                if not ((question_str == "what color is the hydrant" and ("img1" in path_img or "img2" in path_img)) or
                        (question_str == "why are the men jumping to catch" and ("img3" in path_img or "img4" in path_img)) or
                        (question_str == "is the water still" and ("img5" in path_img or "img6" in path_img)) or
                        (question_str == "how many people are in the image" and ("img7" in path_img or "img8" in path_img))):
                    continue

            print(
                "\n\n=========================================================================")
            print("{} - {}".format(question_str, path_img))

            if dataset == "vqa2":
                ans_gt = "red"
            else:
                ans_gt = get_answer(dataset, path_img, question_str)

            if ans_gt is None:
                continue
            else:
                input_size = 256
                step = 2
                windows_size = 32

                dst_dir = "temp/occlusion"
                paths_utils.make_dir(dst_dir)
                out_color_path = "{}/{}_{}_w_{:0}_s_{:0}_color.jpg".format(dst_dir,
                                                                           paths_utils.get_filename_without_extension(
                                                                               path_img),
                                                                           question_str.replace(
                                                                               ' ', '_'),
                                                                           windows_size,
                                                                           step
                                                                           )
                out_gray_path = "{}/{}_{}_w_{:0}_s_{:0}_gray.jpg".format(dst_dir,
                                                                         paths_utils.get_filename_without_extension(
                                                                             path_img),
                                                                         question_str.replace(
                                                                             ' ', '_'),
                                                                         windows_size,
                                                                         step
                                                                         )
                out_avg_path = "{}/{}_{}_w_{:0}_s_{:0}_avg.jpg".format(dst_dir,
                                                                       paths_utils.get_filename_without_extension(
                                                                           path_img),
                                                                       question_str.replace(
                                                                           ' ', '_'),
                                                                       windows_size,
                                                                       step
                                                                       )

                if not os.path.exists(out_color_path):

                    visual_PIL = Image.open(path_img)
                    indices = np.asarray(
                        np.mgrid[0:input_size-windows_size+1:step, 0:input_size-windows_size+1:step].reshape(2, -1).T, dtype=np.int)

                    cnn, model, trainset = initialize(args, dataset=dataset)
                    # cnn, model, trainset = None, None, None

                    image_occlusion = np.zeros((input_size, input_size))
                    image_occlusion_times = np.zeros((input_size, input_size))

                    ans_without_black_patch = process_one_batch_of_occlusion(args,
                                                                             cnn,
                                                                             model,
                                                                             trainset,
                                                                             visual_PIL,
                                                                             question_str,
                                                                             list_box=None,
                                                                             dataset=dataset)

                    try:
                        score_without_black_patch = ans_without_black_patch[0].get("val")[
                            ans_without_black_patch[0].get("ans").index(ans_gt)]
                    except:
                        score_without_black_patch = torch.tensor(0)

                    batch = 32
                    count = 0
                    list_box = []
                    for i in range(indices.shape[0]):
                        print_utils.print_tqdm(i, indices.shape[0])
                        list_box.append([indices[i][0], indices[i][0]+windows_size -
                                         1, indices[i][1], indices[i][1]+windows_size-1])
                        count += 1

                        # if count == batch or i == indices.shape[0] - 1:
                        if count == batch:
                            # print(count)
                            ans = process_one_batch_of_occlusion(args,
                                                                 cnn,
                                                                 model,
                                                                 trainset,
                                                                 visual_PIL,
                                                                 question_str,
                                                                 list_box,
                                                                 dataset=dataset,
                                                                 is_print=False)

                            for i in range(len(list_box)):
                                try:
                                    score = ans[i].get("val")[
                                        ans[i].get("ans").index(ans_gt)]
                                except:
                                    score = 0
                                box = list_box[i]

                                if score != 0:
                                    try:
                                        score_occ = (
                                            score.item() - score_without_black_patch.item())/score_without_black_patch.item()
                                    except:
                                        score_occ = 0
                                    image_occlusion[box[0]:box[1],
                                                    box[2]:box[3]] += score_occ
                                    image_occlusion_times[box[0]:box[1],
                                                          box[2]:box[3]] += 1

                            count = 0
                            list_box = []

                    save_image(visual_PIL, image_occlusion, image_occlusion_times,
                               out_color_path, out_gray_path, out_avg_path,
                               is_show=False)


def main():
    # dataset = "breast"
    # dataset = "tools"

    # dataset = "breast"
    # path = get_path(PROJECT_DIR, dataset)
    # process_occlusion(path, dataset=dataset)
    # dataset = "tools"
    # path = get_path(PROJECT_DIR, dataset)
    # process_occlusion(path, dataset=dataset)
    # dataset = "idrid"
    # path = get_path(PROJECT_DIR, dataset)
    # process_occlusion(path, dataset=dataset)

    dataset = "vqa2"
    path = get_path(PROJECT_DIR, dataset)
    process_occlusion(path, dataset=dataset)


if __name__ == '__main__':
    main()
