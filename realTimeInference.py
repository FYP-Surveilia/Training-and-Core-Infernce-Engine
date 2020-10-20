import cv2
import numpy as np
import argparse
from PIL import Image
import torchvision
import torch.nn.parallel
import torch.optim
from ops.models import TSN
from ops.transforms import * 
from torch.nn import functional as F
import os
import time
from torchsummary import summary


"""
	provide --arch argument to
	shift between architectures
"""

if torch.cuda.is_available():
    print("\nYou have an ",torch.cuda.get_device_name(0)," (Cuda enabled GPU)")
    GPU_FLAG = input("USE GPU (y/n) : ")
    
else:
    print("NO GPU found, Running on CPU!")
    GPU_FLAG = 'n'
startime = time.time()
parser = argparse.ArgumentParser(description="TSM Testing on real time!!")
parser.add_argument('-f',type=str,help='Provide a video!!')
parser.add_argument('--arch',type=str,help='provide architecture [mobilenetv2,resnet50]',default='resnet50')

print()

#just adding some comments to check git 
def parse_shift_option_from_log_name(log_name):
    if 'shift' in log_name:
        strings = log_name.split('_')
        for i, s in enumerate(strings):
            if 'shift' in s:
                break
        return True, int(strings[i].replace('shift', '')), strings[i + 1]
    else:
        return False, None, None

#args = parser.parse_args()
args = vars(parser.parse_args())
if args.get('arch') == 'mobilenetv2':
    this_weights='checkpoint/TSM_ucfcrime_RGB_mobilenetv2_shift8_blockres_avg_segment8_e25/ckpt.best.pth.tar'
else:
    this_weights='checkpoint/TSM_ucfcrime_RGB_resnet50_shift8_blockres_avg_segment8_e25/ckpt.best.pth.tar'

is_shift, shift_div, shift_place = parse_shift_option_from_log_name(this_weights)
modality = 'RGB'

if 'RGB' in this_weights:
	modality = 'RGB'

# Get dataset categories.
categories = ['Normal Activity','Abnormal Activity']
num_class = len(categories)
this_arch = args.get('arch')
print("[INFO] >> Model loading weights from disk!!")

net = TSN(num_class, 1, modality,
              base_model=this_arch,
              consensus_type='avg',
              img_feature_dim='225',
              #pretrain=args.pretrain,
              is_shift=is_shift, shift_div=shift_div, shift_place=shift_place,
              non_local='_nl' in this_weights,
              )

if GPU_FLAG == 'y':
    checkpoint = torch.load(this_weights)
else:
    checkpoint = torch.load(this_weights,map_location=torch.device('cpu'))


checkpoint = checkpoint['state_dict']

# base_dict = {('base_model.' + k).replace('base_model.fc', 'new_fc'): v for k, v in list(checkpoint.items())}
base_dict = {'.'.join(k.split('.')[1:]): v for k, v in list(checkpoint.items())}
replace_dict = {'base_model.classifier.weight': 'new_fc.weight',
                    'base_model.classifier.bias': 'new_fc.bias',
               }
for k, v in replace_dict.items():
    if k in base_dict:
        base_dict[v] = base_dict.pop(k)
net.load_state_dict(base_dict)

print("\n[INFO] >> Model loading Successfull")

if GPU_FLAG == 'y':
    net.cuda().eval()
    skip_frames = 2
    summary(net,(1,3,224,224))
else:
    net.eval()
    skip_frames = 4

transform=torchvision.transforms.Compose([
                           Stack(roll=(this_arch in ['BNInception', 'InceptionV3'])),
                           ToTorchFormatTensor(div=(this_arch not in ['BNInception', 'InceptionV3'])),
                           GroupNormalize(net.input_mean, net.input_std),
                       ])

WINDOW_NAME = 'Real-Time Video Action Recognition'

##ToDo: Save Snapshot when anaomly occurs:
def saveSnapShot(img):
    pass
    
def recordAnaomlousEvent():
    pass


#get max abnormal prob not an efficient way may use to much ram
maxAbnormalProb =[-1]
FpsList = []
estFps = None
maxFps = None
def doInferecing(cap):
    
# set a lower resolution for speed up
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

    # env variables
    full_screen = False
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, 640, 480)
    cv2.moveWindow(WINDOW_NAME, 0, 0)
    cv2.setWindowTitle(WINDOW_NAME, WINDOW_NAME)
    t = None
    i_frame = -1
    count = 0
    print("Ready!")



    while cap.isOpened():
        i_frame += 1
        hasFrame, img = cap.read()  # (480, 640, 3) 0 ~ 255
        img=cv2.flip(img,180)
        
            
        if hasFrame:
            
            img_tran = transform([Image.fromarray(img).convert('RGB')])
            if i_frame % skip_frames == 0:  # skip every other frame to obtain a suitable frame rate  
                t1 = time.time()
            
                if GPU_FLAG == 'y':
                    input1 = img_tran.view(-1, 3, img_tran.size(1),
                    img_tran.size(2)).unsqueeze(0).cuda()
                else:
                    input1 = img_tran.view(-1, 3, img_tran.size(1),
                    img_tran.size(2)).unsqueeze(0)
                       
                input = input1
            
                with torch.no_grad():
                    logits = net(input)
                    h_x = torch.mean(F.softmax(logits, 1), dim=0).data
                    print('<<< [INFO] >>> PROB  - | Normal: {:.2f}'.format(h_x[0]),
                          '| Abnormal: {:.2f} |'.format(h_x[1]),'Frames Rendered-',count,)
                    pr, li = h_x.sort(0, True)
                    probs = pr.tolist()
                    idx = li.tolist()
                    #print(probs)
                    t2 = time.time()
               
                print('<<< [INFO] >>>','EVENT - |',categories[idx[0]],'  Prob: {:.2f}| '.format(probs[0]),'\n')
                current_time = t2 -t1
        
            img = cv2.resize(img, (640, 480))
            img = img[:, ::-1]
            height, width, _ = img.shape
            label = np.zeros([height // 5, width, 3]).astype('uint8') + 255
        
            if categories[idx[0]] == 'Abnormal Activity':
                R = 255
                G = 0  
                maxAbnormalProb.append(float(probs[0]))
            else:
                R = 0
                G = 255
            
            cv2.putText(label, 'EVENT: ' + categories[idx[0]],
                       (10, int(height / 16)),
                       cv2.FONT_HERSHEY_SIMPLEX,
                       0.7, (0, int(G), int(R)), 2)
        
            cv2.putText(label, 'Confidence: {:.2f}%'.format(probs[0]*100,'%'),
                       (width - 250 , int(height / 16)),
                       cv2.FONT_HERSHEY_SIMPLEX,
                       0.7, (0, int(G), int(R)), 2)
        
            fps = 1 / current_time
            #if args.get('f',True):
            FpsList.append(float(fps))
            maxFps=max(FpsList)
            estFps=sum(FpsList)/len(FpsList)
            #else:
                #maxFps=-1
                #estFps=-1
            cv2.putText(label, 'FPS: {:.1f} Frame/s'.format(fps),
                       (10, int(height / 6)),
                       cv2.FONT_HERSHEY_SIMPLEX,
                       0.7, (0, 0, 0), 2)
                  
            img = np.concatenate((img, label), axis=0)
            cv2.imshow(WINDOW_NAME, img)
            #print('-'*20)
            key = cv2.waitKey(1)
        
            if key & 0xFF == ord('q') or key == 27:  # exit
                break
            elif key == ord('F') or key == ord('f'):  # full screen
                print('Changing full screen option!')
                full_screen = not full_screen
                if full_screen:
                    print('Setting FS!!!')
                    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN,
                                          cv2.WINDOW_FULLSCREEN)
                else:
                    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN,
                                          cv2.WINDOW_NORMAL)
            #resetting time for next frame
            if t is None:
                t = time.time()
            else:
                nt = time.time()
                count += 1
                t = nt
            #exit(0)
        else:       
            #i_frame = 0
            #cap.set(cv2.CAP_PROP_POS_FRAMES,0)
            cap.release()
            cv2.destroyAllWindows()
            #Clearing Variables for re-running
            #estFps=None
            #maxAbnormalProb.clear()
            #maxFps=None
            
            
    execTime = time.time() - startime
    print()
    
    print('<<< [INFO] >>> Total Abnormal Probs : ',len(maxAbnormalProb))
    print('<<< [INFO] >>> Max Abnormality Prob : {:.2f}'.format(max(maxAbnormalProb)))
    print('<<< [INFO] >>> Max FPS achieved     : {:.1f}'.format(maxFps))
    print('<<< [INFO] >>> Averge Estimated FPS : {:.1f}'.format(estFps)) 
    print('<<< [INFO] >>> Total Infernece Time : {:.2f} seconds'.format(execTime))
    
def main():
    #args = vars(parser.parse_args())
    
    if not args.get('f', False):
        print("Openinig camera...")
        cap = cv2.VideoCapture(0)
        
        #cap = cv2.VideoCapture('http://192.168.43.1:8080/video')
        
    else:
        print("loading Video...")
        cap = cv2.VideoCapture(args['f'])
        
    doInferecing(cap)

main()
