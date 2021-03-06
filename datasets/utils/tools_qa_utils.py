import itertools
from itertools import product
from operator import itemgetter

def find_list_tools_in_boxes(boxes):
    list_tools = []
    for i in range(len(boxes)):
        tool, xmin1, xmax1, ymin1, ymax1 = boxes[i]
        list_tools.append(tool)
    return list_tools


def find_all_combination_of_two_lists(list1, is_unique=True):
    if is_unique:
        return [(x, y) for x, y in product(*list1) if x != y]
    else:
        return [(x, y) for x, y in product(*list1)]


def generate_ques_how_many_tools():
    return "how many tools are there?"


def get_ans_how_many_tools(boxes):
    return len(boxes)


def generate_ques_major_tool():
    return "what is the major tool in the image?"


def compute_area_bb_tool(xmin1, xmax1, ymin1, ymax1):
    return (xmax1-xmin1)*(ymax1-ymin1)


def get_ans_major_tool(boxes):
    if len(boxes) == 1:
        return boxes[0][0].lower()
    if len(boxes) > 1:
        areas = list()
        for i in range(len(boxes)):
            tool, xmin1, xmax1, ymin1, ymax1 = boxes[i]
            areas.append(compute_area_bb_tool(xmin1, xmax1, ymin1, ymax1))
        index_max_area = areas.index(max(areas))
        return boxes[index_max_area][0].lower()


def generate_ques_minor_tool():
    return "what is the minor tool in the image?"


def get_ans_minor_tool(boxes):
    if len(boxes) == 1:
        return "na"
    if len(boxes) > 1:
        areas = list()
        for i in range(len(boxes)):
            tool, xmin1, xmax1, ymin1, ymax1 = boxes[i]
            areas.append(compute_area_bb_tool(xmin1, xmax1, ymin1, ymax1))
        index_min_area = areas.index(min(areas))
        return boxes[index_min_area][0].lower()


def generate_ques_is_x_larger_or_smaller_than_y(x, data=""):
    combinations = find_all_combination_of_two_lists(x)
    q = list()
    for i in range(len(combinations)):
        t1 = combinations[i][0]
        t2 = combinations[i][1]
        if data == "":
            ques = "is {} larger than {}".format(t1, t2)
            q.append(ques.lower())
            ques = "is {} smaller than {}".format(t1, t2)
            q.append(ques.lower())
        else:
            ques = "is {}'s {} larger than {}'s".format(t1, data, t2)
            q.append(ques.lower())
            ques = "is {}'s {} smaller than {}'s".format(t1, data, t2)
            q.append(ques.lower())
    return q, combinations


def get_one_ans_is_x_larger_than_y(combination, boxes):
    major_tool = get_ans_major_tool(boxes)
    minor_tool = get_ans_minor_tool(boxes)
    t1 = combination[0]
    t2 = combination[1]
    if major_tool == t1 and minor_tool == t2:
        return "yes"
    elif major_tool == t2 and minor_tool == t1:
        return "no"
    else:
        return "na"


def get_ans_is_x_larger_or_smaller_than_y(combinations, boxes):
    a = list()
    for i in range(len(combinations)):
        t1 = combinations[i][0]
        t2 = combinations[i][1]
        ans_larger = get_one_ans_is_x_larger_than_y([t1, t2], boxes)
        ans_smaller = get_one_ans_is_x_larger_than_y([t2, t1], boxes)
        a.append(ans_larger)
        a.append(ans_smaller)
    return a


def generate_ques_is_there_any_x(x):
    q = list()
    for i in range(len(x)):
        ques = "is there any {} in the image?".format(x[i])
        q.append(ques.lower())
    return q


def get_ans_is_there_any_x(x, boxes):
    list_tools = find_list_tools_in_boxes(boxes)
    a = list()
    for i in range(len(x)):
        if x[i] in list_tools:
            a.append("yes")
        else:
            a.append("no")
    return a


def is_two_boxes_overlap(box1, box2):
    # input:
    # 1D
    # box1 = (xmin1, xmax1)
    # box2 = (xmin2, xmax2)
    # 2D
    # box1 = (x:(xmin1,xmax1),y:(ymin1,ymax1))
    # box2 = (x:(xmin2,xmax2),y:(ymin2,ymax2))
    # 3D
    # box1 = (x:(xmin1,xmax1),y:(ymin1,ymax1),z:(zmin1,zmax1))
    # box2 = (x:(xmin2,xmax2),y:(ymin2,ymax2),z:(zmin2,zmax2))
    def overlapping1D(xmin1, xmax1, xmin2, xmax2):
        return xmax1 >= xmin2 and xmax2 >= xmin1

    def overlapping2D(box1, box2):
        xmin1, xmax1, ymin1, ymax1 = box1
        xmin2, xmax2, ymin2, ymax2 = box2
        return overlapping1D(xmin1, xmax1, xmin2, xmax2) and overlapping1D(ymin1, ymax1, ymin2, ymax2)

    return overlapping2D(box1, box2)


def generate_encoded_box_location(image_shape, box_size=32):
    h, w = image_shape
    _h = list(range(0, h, box_size))
    _w = list(range(0, w, box_size))
    list1 = _h, _w
    combinations = find_all_combination_of_two_lists(list1, is_unique=False)
    encoded_locations = list()
    for i in range(len(combinations)):
        x, y = combinations[i]
        ques = str("{}_{}_{}_{}".format(x, y, box_size, box_size))
        encoded_locations.append(ques)
    return encoded_locations


def decode_encoded_location(encoded_location):
    split = encoded_location.split('_')
    split = [int(x) for x in split]
    xmin1, ymin1, box_size, box_size = split
    return [xmin1, xmin1+box_size, ymin1, ymin1+box_size]


def generate_ques_is_x_in_z(x, image_shape):
    encoded_locations = generate_encoded_box_location(image_shape, box_size=32)
    q = list()
    for i in range(len(encoded_locations)):
        for j in range(len(x)):
            ques = "is {} in {} location?".format(x[j], encoded_locations[i])
            q.append(ques.lower())
    return q, encoded_locations


def get_ans_is_x_in_z(x, encoded_locations, boxes):
    a = list()
    for i in range(len(encoded_locations)):
        for j in range(len(x)):
            tool = x[j]
            decoded_location = decode_encoded_location(encoded_locations[i])
            ans = "no"
            for k in range(len(boxes)):
                tool_box, xmin1, xmax1, ymin1, ymax1 = boxes[k]
                if tool == tool_box and is_two_boxes_overlap(decoded_location, [xmin1, xmax1, ymin1, ymax1]):
                    ans = "yes"
            a.append(ans.lower())
    return a


def get_tool_position(boxes):
    keys = ["left", "right", "top", "bottom"]
    values = list()

    tools = list()
    xmid = list()
    ymid = list()
    for i in range(len(boxes)):
        tools.append(boxes[i][0])
        xmid.append(boxes[i][2]-boxes[i][1])
        ymid.append(boxes[i][4]-boxes[i][3])

    min_xmid_idx = min(enumerate(xmid), key=itemgetter(1))[0]
    max_xmid_idx = max(enumerate(xmid), key=itemgetter(1))[0]
    min_ymid_idx = min(enumerate(ymid), key=itemgetter(1))[0]
    max_ymid_idx = max(enumerate(ymid), key=itemgetter(1))[0]

    values.extend([tools[min_xmid_idx], tools[max_xmid_idx], tools[min_ymid_idx], tools[max_ymid_idx]])

    return dict(zip(keys, values))


def generate_ques_which_tool_pointed_tip_position():
    q = list()
    position_list = ["on the left", "on the right",
                     "at the top", "at the bottom"]
    for i in range(len(position_list)):
        ques = "which tool having pointed tip {} of the image?".format(
            position_list[i])
        q.append(ques.lower())
    return q


def get_ans_which_tool_pointed_tip_position(boxes):
    num_tools = get_ans_how_many_tools(boxes)
    a = list()
    if num_tools == 1:
        for i in range(4):
            a.append("na")
    else:
        positions = get_tool_position(boxes)
        a.append(positions.get("left", "na"))
        a.append(positions.get("right", "na"))
        a.append(positions.get("top", "na"))
        a.append(positions.get("bottom", "na"))
    return a
