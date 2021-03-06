import argparse
import torch
import torch.nn as nn
import torch.utils.data as data
import torch.optim as opt
from torchvision import models
from torchvision.models.detection import FasterRCNN, fasterrcnn_resnet50_fpn
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from facenet_pytorch import MTCNN, InceptionResnetV1
import utils
from GPU import get_device
from dataloader import load_dataset
from trainer import train




if __name__ == "__main__":
    # parser
    parser = argparse.ArgumentParser()
    parser.add_argument("--detection", dest='detection', action='store_true',
                        help="Training object detection")
    parser.add_argument("--train_mode", dest='mode', action='store',
                        help="Training mode: from_scratch, finetune, small_net, faster_rcnn, mtcnn")
    parser.add_argument("--num_epoch", dest='num_epochs', action='store', type=int,
                        help="Number of Epochs")
    parser.add_argument("--learning_rate", dest='lr', action='store', type=float,
                        help="Learning rate")
    parser.add_argument("--adaptive_learning", dest='steps_epochs', action='store', nargs='+', type=int,
                        help="Epochs at which to drop the learning rate by factor 10")
    parser.add_argument("--batch_size", dest='batch_size', action='store', type=int,
                        help="Batch size for training")
    parser.add_argument("--num_workers", dest='num_workers', action='store', type=int,
                        help="Number of workers for dataloader")
    parser.add_argument("--no_pin_memory", dest="pin_memory", action='store_false',
                        help="Disable pin memory")

    parser.set_defaults(detection=False, mode='from_scratch', layer=None, num_epochs=100, lr=1e-3,
                        steps_epochs=[50, 80, 100], batch_size=128, num_workers=0, pin_memory=True)
    args = parser.parse_args()

    # check if GPU available
    device = get_device()

    # load data
    if args.detection:
        if args.mode == 'mtcnn':
            trainset, testset = load_dataset('cropped')
            print("Load cropped image dataset")
        else:
            trainset, testset = load_dataset('detection')
            print("Load object detection dataset")
    else:
        trainset, testset = load_dataset('single_person')
        print("Load single person dataset")

    # dataloader
    if args.mode == 'faster_rcnn':
        trainloader = data.DataLoader(trainset, args.batch_size, True, num_workers=args.num_workers,
                                  pin_memory=args.pin_memory, collate_fn=utils.collate_fn)
        testloader = data.DataLoader(testset, args.batch_size, collate_fn=utils.collate_fn)
    else:
        trainloader = data.DataLoader(trainset, args.batch_size, True, num_workers=args.num_workers,
                                      pin_memory=args.pin_memory)
        testloader = data.DataLoader(testset, args.batch_size)

    if args.detection:
        print("Initialize Training Mode: {}".format(args.mode))
        if args.mode == 'mtcnn':
            # model
            #mtcnn = MTCNN(image_size=224, keep_all=True, device=device)
            model = InceptionResnetV1(pretrained='vggface2', classify=True, num_classes=3).to(device)
        elif args.mode == 'faster_rcnn':
            # model
            model = fasterrcnn_resnet50_fpn(pretrained=True).to(device)
            in_feat = model.roi_heads.box_predictor.cls_score.in_features
            model.roi_heads.box_predictor = FastRCNNPredictor(in_feat, 4).to(device)
        else:
            print("Error: Training Mode {} is not defined for detection dataset!".format(args.mode))
    else:
        # set mode to transfer learning, if layer number of mobilenet is given
        if args.layer is not None:
            args.mode = 'transfer'

        # model
        print("Initialize Training Mode: {}".format(args.mode))
        if args.mode == 'from_scratch':
            model = models.mobilenet_v2(pretrained=False).features.to(device)
            model.classifier = nn.Sequential(nn.Dropout(p=0.2, inplace=False),
                                             nn.Flatten(),
                                             nn.Linear(1280*7*7, 2, bias=True)).to(device)
        elif args.mode == 'finetune':
            model = models.mobilenet_v2(pretrained=True).features.to(device)
            model.classifier = nn.Sequential(nn.Dropout(p=0.2, inplace=False),
                                             nn.Flatten(),
                                             nn.Linear(1280*7*7, 2, bias=True)).to(device)
        elif args.mode == 'small_net':
            model = nn.Sequential(nn.Flatten(),
                                  nn.Linear(3*224*224, 100, bias=True),
                                  nn.ReLU(),
                                  nn.Linear(100, 100, bias=True),
                                  nn.ReLU(),
                                  nn.BatchNorm1d(100),
                                  nn.Dropout(0.2),
                                  nn.Linear(100, 2)).to(device)
        else:
            print("Error: Training Mode {} is not defined!".format(args.mode))

    # optimizer
    optimizer = opt.SGD(model.parameters(), lr=args.lr, momentum=0.9, weight_decay=0.0005)

    # criterion
    criterion = nn.CrossEntropyLoss()

    # scheduler
    scheduler = opt.lr_scheduler.MultiStepLR(optimizer, args.steps_epochs, 0.1)

    # training
    train(model, trainloader, testloader, criterion, optimizer, scheduler, args.num_epochs, device, args.mode,
          args.detection)

    # free GPU space
    del model
    torch.cuda.empty_cache()





