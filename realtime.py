import os
import sys
import json
import datetime
import numpy as np
import skimage.draw
import random
import itertools
import colorsys
import cv2
from time import sleep
from tqdm import tqdm
import math
import time

from utility.player_utility import *
from statistics import Statistics

# Root directory of the project
ROOT_DIR = os.path.abspath("../../")
prev_det = [0,0]

# Import Mask RCNN
sys.path.append(ROOT_DIR)  # To find local version of the library
from mrcnn.config import Config
from mrcnn import model as modellib, utils
from mrcnn import visualize

# Path to trained weights file
COCO_WEIGHTS_PATH = os.path.join(ROOT_DIR, "mask_rcnn_coco.h5")

# Directory to save logs and model checkpoints, if not provided
# through the command line argument --logs
DEFAULT_LOGS_DIR = os.path.join(ROOT_DIR, "logs")

# Import COCO config
sys.path.append(os.path.join(ROOT_DIR, "samples/coco/"))  # To find local version
import coco

# Different classes for different train
ball_class = ['BG', 'basketball']
coco_class = ['BG', 'person', 'bicycle', 'car', 'motorcycle', 'airplane',
    'bus', 'train', 'truck', 'boat', 'traffic light',
    'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird',
    'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear',
    'zebra', 'giraffe', 'backpack', 'umbrella', 'handbag', 'tie',
    'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball',
    'kite', 'baseball bat', 'baseball glove', 'skateboard',
    'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup',
    'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
    'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza',
    'donut', 'cake', 'chair', 'couch', 'potted plant', 'bed',
    'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote',
    'keyboard', 'cell phone', 'microwave', 'oven', 'toaster',
    'sink', 'refrigerator', 'book', 'clock', 'vase', 'scissors',
    'teddy bear', 'hair drier', 'toothbrush']

# Base config for ball detection
class BasketConfig(Config):
    NAME = "basket"
    IMAGES_PER_GPU = 2
    NUM_CLASSES = 1 + 1  # Background + basketball
    STEPS_PER_EPOCH = 175
    DETECTION_MIN_CONFIDENCE = 0.94
    BACKBONE = 'resnet50'
    DETECTION_NMS_THRESHOLD = 0.2
    RPN_ANCHOR_SCALES = (16, 32, 64, 128, 256)
    WEIGHT_DECAY = 0.005

# define random colors
def random_colors(N):
    np.random.seed(1)
    colors = [tuple(255 * np.random.rand(3)) for _ in range(N)]
    return colors

#Take the image and apply the mask, box, and Label
def player_instances(count, image, boxes, masks, ids, names, scores, resize):
    f = open("det/det_player_maskrcnn.txt", "a")

    n_instances = boxes.shape[0]
    colors = random_colors(n_instances)

    color_list = []
    players_boxes = []
    players_id = []

    if not n_instances:
        return image, [], []
    else:
        assert boxes.shape[0] == masks.shape[-1] == ids.shape[0]
        
    for i, color in enumerate(colors):
        if not np.any(boxes[i]):
            continue

        y1, x1, y2, x2 = boxes[i] * resize
        label = names[ids[i]]
        score = scores[i] if scores is not None else None

        width = x2 - x1
        height = y2 - y1
        
        #If a player
        if score > 0.75 and label == 'person':
            mask = masks[:, :, i]

            #Create a masked image where the pixel not in mask is green
            image_to_edit = image.copy()
            mat_mask = cut_by_mask(image_to_edit, mask)

            offset_w = int(width/6)
            offset_h = int(height/3)
            offset_head = int(height/8)

            #Crop the image with some defined offset
            crop_img = mat_mask[y1+offset_head:y2-offset_h, x1+offset_w:x2-offset_w]

            #Return one single dominant color
            rgb_color = get_dominant(crop_img)

            #Add to the list of all the bbox color found in the single frame
            color_list.append(rgb_color)

            rgb_tuple = tuple([int(rgb_color[0]), int(rgb_color[1]), int(rgb_color[2])]) 

            caption = '{} {:.2f}'.format(label, score) if score else label
        
            team = getTeam(image, rgb_color)

            if team == 1: 
                box_color = (60,60,60)
            elif team == 2:
                box_color = (200, 200, 200) 
            else: 
                box_color = [0, 102, 204, 0]

            image = apply_mask(image, mask, rgb_tuple)
            image = cv2.rectangle(image, (x1, y1), (x2, y2), box_color, 3)
            image = cv2.putText(image, caption, (x1, y1 - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.8, box_color, 2)

            players_boxes.append([x1, y1, (x2 - x1), (y2 - y1)])
            players_id.append(team)

            f.write('{},-1,{},{},{},{},{},-1,-1,-1,{} \n'.format(count, x1, y1, (x2 - x1), (y2 - y1), score, team))

    if len(color_list) > 3:
        #Group to 3 cluster all the color found in the frame's bboxes
        clusters, counts = parse_colors(color_list, 3)

        #Update team's stats
        image = draw_team(image, clusters, counts)

    f.close()

    return image, players_boxes, players_id

#take the image and apply the mask, box, and Label
def ball_instances(count, image, boxes, masks, ids, names, scores, resize):
    f = open("det/det_maskrcnn.txt", "a")

    #Finetuning of the ball detection to avoid outsiders
    min_ball_size = 10
    max_ball_size = 1500

    n_instances = boxes.shape[0]
    colors = random_colors(n_instances)

    best_index = -1
    best_score = 0

    dict_result = []

    if not n_instances:
        return image, []
        #print('NO INSTANCES TO DISPLAY')
    else:
        assert boxes.shape[0] == masks.shape[-1] == ids.shape[0]
        
    for i, color in enumerate(colors):
        if not np.any(boxes[i]):
            continue

        y1, x1, y2, x2 = boxes[i] * resize
        label = names[ids[i]]
        score = scores[i] if scores is not None else None

        width = x2 - x1
        height = y2 - y1

        area = width * height

        if score > 0.90: 
            label = names[ids[i]]
            caption = '{} {:.2f}'.format(label, score) if score else label
            mask = masks[:, :, i]
            #image = apply_mask(image, mask, (0,255,0))
            #image = cv2.rectangle(image, (x1, y1), (x2, y2), (0,255,0), 1)
            #image = cv2.putText(image, caption, (x1, y1), cv2.FONT_HERSHEY_COMPLEX, 0.7, (0,255,0), 2)

        if score > 0.90 and min_ball_size < area < max_ball_size:
            if score > best_score: 
                best_score = score
                best_index = i

    if best_index >= 0:
        y1, x1, y2, x2 = boxes[best_index] * resize
        label = names[ids[best_index]]
        caption = '{} {:.2f}'.format(label, score) if best_score else label
        mask = masks[:, :, best_index]
        #image = apply_mask(image, mask, (255,0,0))
        #image = cv2.rectangle(image, (x1, y1), (x2, y2), (255, 0,0), 5)
        #image = cv2.putText(image, "BALL", (x1, y1), cv2.FONT_HERSHEY_COMPLEX, 0.8, (255,0,0), 2)

        dict_result = [x1, y1, (x2 - x1), (y2 - y1), best_score]

        f.write('{},-1,{},{},{},{},{},-1,-1,-1\n'.format(count, x1, y1, (x2 - x1), (y2 - y1), best_score))

    f.close()

    return image, dict_result

def video_detection(stat, ball_model, player_model, video_path, txt_path="det/det_track_maskrcnn.txt", resize=1, display=False):
    f = open("det/det_player_maskrcnn.txt", "w").close()
    f = open("det/det_maskrcnn.txt", "w").close()
    f = open(txt_path, "w")

    # Video capture
    vcapture = cv2.VideoCapture(video_path)
    width = int(vcapture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(vcapture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = vcapture.get(cv2.CAP_PROP_FPS)
    length_input = int(vcapture.get(cv2.CAP_PROP_FRAME_COUNT))

    print("Totale frame: {}".format(length_input))

    # Define codec and create video writer
    file_name = "output/full_detection_{:%Y%m%dT%H%M%S}.mp4".format(datetime.datetime.now())
    vwriter = cv2.VideoWriter(file_name,
                                cv2.VideoWriter_fourcc(*'mp4v'),
                                fps, (int(width/resize), int(height/resize)))
    
    count = 1
    success = True
    total_det = 0

    params = cv2.TrackerCSRT_Params()
    params.psr_threshold = 0.08

    tracker = cv2.TrackerCSRT_create(params)

    initBB = None
    bbox_offset = 10
    prev_box = [0, 0]

    frame_diff = 0
    tracked_box = [0,0,0,0]

    start = time.time()
    _, first = vcapture.read()

    # Draw central line
    stat.initialize(first, resize)

    with tqdm(total=length_input, file=sys.stdout) as pbar:
        while success:
            success, image = vcapture.read()
            if success:
                image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                c_image = image.copy()
                ball_image = image.copy()
                track_image = image.copy()

                #Mask for LATERAL VIEW GAME ONLY!
                mask = get_mask('roi_mask_undistorted.jpg')
                mask = np.expand_dims(mask,2)
                mask = np.repeat(mask,3,2)

                #Apply pitch mask to esclude the people outside
                masked_pitch = image * mask
                masked_pitch = masked_pitch.astype(np.uint8)

                #Reduce computing impact
                #masked_pitch = cv2.resize(masked_pitch, (int(width/resize), int(height/resize)))
                image = cv2.resize(image, (int(width/resize), int(height/resize)))
                
                # Apply detections model
                ball_ret = ball_model.detect([ball_image], verbose=0)[0]
                player_ret = player_model.detect([masked_pitch], verbose=0)[0]

                # Draw and save bbox result
                # Process player
                frame, p_boxes, p_id = player_instances(count, c_image, player_ret["rois"], player_ret["masks"], player_ret["class_ids"], coco_class, player_ret["scores"], 1)

                # Process ball and start tracker
                _, detection = ball_instances(count, frame, ball_ret["rois"], ball_ret["masks"], ball_ret["class_ids"], ball_class, ball_ret["scores"], resize)

                #Tracking phase
                if detection != []:
                    coor = np.array(detection[:4], dtype=np.int32)
                    if initBB is None or (prev_box[0] == 0 and prev_box[1] == 0):
                        initBB = (coor[0] - bbox_offset, coor[1] - bbox_offset, coor[2] + 2*bbox_offset, coor[3] + 2*bbox_offset)
                        tracker = cv2.TrackerCSRT_create(params)
                        tracker.init(track_image, initBB)
                    else:
                        min_distance = 99999
                        initBB = (coor[0] - bbox_offset, coor[1] - bbox_offset, coor[2] + 2*bbox_offset, coor[3] + 2*bbox_offset)
                        eucl = math.sqrt((coor[0] - prev_box[0]) ** 2 + (coor[1] - prev_box[1]) ** 2)  
                    
                        if frame_diff > 6 or eucl < 200: 
                            tracker = cv2.TrackerCSRT_create(params)
                            tracker.init(track_image, initBB)

                            frame_diff = 0        
                        else:
                            frame_diff += 1
                            
                # If there is a new bbox, update the tracker
                if initBB is not None: 
                    (track_success, tracked_box) = tracker.update(track_image)

                    if track_success:
                        #Save tracking boxes (include also det)
                        f.write('{},-1,{},{},{},{},{},-1,-1,-1\n'.format(count, tracked_box[0], tracked_box[1], tracked_box[2], tracked_box[3], 1))
                        prev_box = [tracked_box[0], tracked_box[1]]
                    else: 
                        initBB = None

                # RGB -> BGR to save image to video
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                # FPS calculation
                end = time.time()
                frame_time = end - start

                d_fps = round(count / frame_time, 2)

                #print("FPS: {}".format(d_fps))

                frame = cv2.rectangle(frame, (width - 200, 50), (width - 50, 150), (0,0,0), -1)
                frame = cv2.putText(frame, "{}".format(d_fps), (width - 170, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (230,230,230), 2)

                # Generate stats
                stat_image = stat.run_stats(frame, [tracked_box], p_boxes, p_id, fps, count)

                # Draw tracked ball here for z-index reason
                p1 = (int(tracked_box[0]), int(tracked_box[1]))
                p2 = (int(tracked_box[0] + tracked_box[2]), int(tracked_box[1] + tracked_box[3]))
                cv2.rectangle(stat_image, p1, p2, (0, 153, 255), 7, 4)
                cv2.putText(stat_image, "ball", (p1[0], p1[1] - 20), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 153, 255), 3)

                to_save = cv2.resize(stat_image, (int(width/resize), int(height/resize)))
                
                # Add image to video writer
                vwriter.write(to_save)

                if display:
                    to_show = cv2.resize(stat_image, (int(width/2), int(height/2)))
                    cv2.imshow('Real time processing', to_show)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
    
                count += 1

            #Fancy print
            pbar.update(1)
            sleep(0.02)

    vwriter.release()
    print("Saved to ", file_name)

    # Saving complete stats on file
    stat_file = open("stats/full_stat.txt", "w")
    #stat.generate_file(stat_file, count)
    stat_file.close()

    # Close tracking bounding save file
    f.close()

if __name__ == '__main__':
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Train Mask R-CNN to detect balloons.')
    parser.add_argument('--weights', required=True,
                        metavar="/path/to/weights.h5",
                        help="Path to weights .h5 file or 'coco'")
    parser.add_argument('--logs', required=False,
                        default=DEFAULT_LOGS_DIR,
                        metavar="/path/to/logs/",
                        help='Logs and checkpoints directory (default=logs/)')
    parser.add_argument('--video', required=True,
                        metavar="path or URL to video",
                        help='Video to apply the color splash effect on')
    parser.add_argument('-d', '--display', required=False, action='store_true')
    args = parser.parse_args()

    class BallConfig(BasketConfig):
        GPU_COUNT = 1
        IMAGES_PER_GPU = 1
    class PlayerConfig(coco.CocoConfig):
        BACKBONE = 'resnet101'
        DETECTION_MIN_CONFIDENCE = 0.82
        GPU_COUNT = 1
        IMAGES_PER_GPU = 1

    ball_config = BallConfig()
    player_config = PlayerConfig()
    #config.display()

    # Create model for ball and player detection
    player_model = modellib.MaskRCNN(mode="inference", config=player_config, model_dir=args.logs)
    ball_model = modellib.MaskRCNN(mode="inference", config=ball_config, model_dir=args.logs)

    # Assign the two weights (coco for the player)
    player_weight = COCO_WEIGHTS_PATH
    ball_weight = args.weights

    # Assign the weights to the model
    player_model.load_weights(player_weight, by_name=True)
    ball_model.load_weights(ball_weight, by_name=True)

    # Initialize statistics object
    stat = Statistics()

    # TODO detection player and ball
    video_detection(stat, ball_model, player_model, video_path=args.video, display=args.display)