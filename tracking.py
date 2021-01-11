import os
import sys
import json
import datetime
import numpy as np
import random
import cv2
import colorsys
import skimage.io
from time import sleep
#from google.colab.patches import cv2_imshow
from imutils.video import FPS
from tqdm import tqdm
import math

#My own library with utils functions
from utility import *

# Root directory of the project
ROOT_DIR = os.path.abspath("../../")

os.environ['CUDA_VISIBLE_DEVICES'] = '0'

# Import Mask RCNN
sys.path.append(ROOT_DIR)  # To find local version of the library

#Tacking using OpenCV implementation of CSRT 
def opencv_tracking(video_path, detection_path):
    #BBOX file path
    f = open("det/det_track_maskrcnn.txt", "w")

    #Open stat file
    stat = open("stats/stat.txt", "a")

    #Convert file detection to dictionary
    gt_dict = get_dict(detection_path)
    
    #Initialize tracker
    tracker = cv2.TrackerCSRT_create()

    # Input video
    video = cv2.VideoCapture(video_path)
    length_input = int(video.get(cv2.CAP_PROP_FRAME_COUNT))

    # Output video
    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
    out = cv2.VideoWriter('output/tracking.avi',fourcc, 30.0, (int(video.get(3)),int(video.get(4))))
    
    if not video.isOpened():
        print ("Could not open video")
        sys.exit()

    file_path = 'tracker_params.yaml'
    fp = cv2.FileStorage(file_path, cv2.FILE_STORAGE_READ)  # Read file
      # Do not use: tracker.read(fp.root())

    frame_id = 0
    ret = True
    success = False
    initBB = None

    det_frame = 0
    track_frame = 0

    fps = None

    prev_box = [0, 0]
    frame_diff = 0

    with tqdm(total=length_input, file=sys.stdout) as pbar:
        while ret:
            ret, frame = video.read()

            if not ret:
                continue

            #Get bbox for single frame
            boxes, scores, names = [], [], []
            boxes,scores,names,complete = get_gt(frame_id,gt_dict)

            (H, W) = frame.shape[:2]

            #Draw the detections boxes 
            frame = draw_bbox(frame, [], complete, show_label=False, tracking=True)

            #Just log for stats
            if len(boxes) > 0:
                det_frame+=1

            if initBB is None or frame_id % 1 == 0:
                min_distance = 9999

                for i, bbox in enumerate(boxes):
                    coor = np.array(bbox[:4], dtype=np.int32)
                    initBB = (coor[0]-6, coor[1]-6, coor[2]+12, coor[3]+12)

                    #Difference between new detections and last tracking by CSRT
                    eucl = math.sqrt((coor[0] - prev_box[0]) ** 2 + (coor[1] - prev_box[1]) ** 2)

                    if (prev_box[0] == 0 and prev_box[1] == 0) or (frame_diff > 3 or eucl < 50): 
                        if eucl < min_distance: 
                            min_distance = eucl
                            
                            tracker = cv2.TrackerCSRT_create()
                            #tracker.read(fp.getFirstTopLevelNode())
                            tracker.init(frame, initBB)
                        
                            fps = FPS().start()

                            frame_diff = 0        
                    else:
                        frame_diff += 1
                            
            if initBB is not None: 
                (success, tracked_box) = tracker.update(frame)
                #(success, tracked_boxes) = trackers.update(frame)

                if success:
                    '''for i, newbox in enumerate(tracked_boxes):
                        p1 = (int(newbox[0]), int(newbox[1]))
                        p2 = (int(newbox[0] + newbox[2]), int(newbox[1] + newbox[3]))
                        cv2.rectangle(frame, p1, p2, (255,0,100), 6, 3)'''

                    #Save tracking boxes (include also det)
                    f.write('{},-1,{},{},{},{},{},-1,-1,-1\n'.format(frame_id, tracked_box[0], tracked_box[1], tracked_box[2], tracked_box[3], 1))
                    track_frame+=1

                    p1 = (int(tracked_box[0]), int(tracked_box[1]))
                    p2 = (int(tracked_box[0] + tracked_box[2]), int(tracked_box[1] + tracked_box[3]))
                    cv2.rectangle(frame, p1, p2, (255,0,100), 6, 3)

                    # update the FPS counter
                    fps.update()
                    fps.stop()

                    prev_box = [tracked_box[0], tracked_box[1]]
                    
                    # initialize the set of information we'll be displaying on
                    # the frame
                    info = [
                        ("Tracker", "CSRT"),
                        ("Success", "Yes" if success else "No"),
                        ("FPS", "{:.2f}".format(fps.fps())),
                    ]
                    
                    # loop over the info tuples and draw them on our frame
                    for (i, (k, v)) in enumerate(info):
                        text = "{}: {}".format(k, v)
                        cv2.putText(frame, text, (16, H - ((i * 25) + 20)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                else: 
                    initBB = None

            #Save video frame
            out.write(frame)    
            frame_id+=1

            #Fancy print
            pbar.update(1)
            sleep(0.1)

    stat.write("Tracking\n")   
    stat.write("Numero tatale frame: {}\n".format(frame_id))
    stat.write("Numero tatale frame con posizione individuata: {}\n".format(det_frame))
    stat.write("Numero tatale frame tracked: {}\n".format(track_frame))

    f.close()

    out.release()
    stat.close()

if __name__ == '__main__':
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Train Mask R-CNN to detect balloons.')
    parser.add_argument('--det', required=True,
                        metavar="/path/to/balloon/dataset/",
                        help='Path to detections file')
    parser.add_argument('--video', required=True,
                        metavar="path or URL to video",
                        help='Video to apply the tracking on')
    args = parser.parse_args()

    print("Video: ", args.video)
    print("Detections: ", args.det)

    opencv_tracking(args.video, args.det)