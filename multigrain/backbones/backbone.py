# Copyright (c) 2015-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the CC-by-NC license found in the
# LICENSE file in the root directory of this source tree.
#
import torch
from torch import nn
import torch.utils.checkpoint
import multigrain
from torchvision.models import resnet18, resnet50, resnet101, resnet152
from pretrainedmodels.models import senet154
from .pnasnet import pnasnet5large
from collections import OrderedDict as OD
from multigrain.modules.layers import Layer
# torch.utils.checkpoint.preserve_rng_state=False


backbone_list = ['resnet18', 'resnet50', 'resnet101', 'resnet152', 'senet154', 'pnasnet5large']


class Features(nn.Module):
    def __init__(self, net):
        super().__init__()
        self.base_net = net

    def forward(self, x):
        return self.base_net.features(x)


class BackBone(nn.Module):
    """
    Base networks with output dict and standarized structure
    Returns embedding, classifier_output
    """
    def __init__(self, net, checkpoint=False, **kwargs):
        super().__init__()
        self.checkpoint = checkpoint
        if isinstance(net, str):
            if net not in backbone_list:
                raise ValueError('Available backbones:', ', '.join(backbone_list))
            net = multigrain.backbones.backbone.__dict__[net](**kwargs)
        children = list(net.named_children())
        self.whitening = None
        self.pre_classifier = None
        if type(net).__name__ == 'ResNet':
            self.features = nn.Sequential(OD(children[:-2]))
            self.pool = children[-2][1]
            self.classifier = children[-1][1]
        elif type(net).__name__ == 'SENet':
            self.features = nn.Sequential(OD(children[:-3]))
            self.pool = children[-3][1]
            self.pre_classifier = children[-2][1]
            self.classifier = children[-1][1]
        elif type(net).__name__ == 'PNASNet5Large':
            self.features = nn.Sequential(Features(net), nn.ReLU())
            self.pool = children[-3][1]
            self.pre_classifier = children[-2][1]
            self.classifier = children[-1][1]
        else:
            raise NotImplementedError('Unknown base net', type(net).__name__)

    def forward(self, input):
        output = {}
        if isinstance(input, list):
            # for lists of tensors of unequal input size
            features = map(self.features, [i.unsqueeze(0) for i in input])
            embedding = torch.cat([self.pool(f) for f in features], 0)
        else:
            if self.checkpoint:
                input.requires_grad = True
                features = torch.utils.checkpoint.checkpoint_sequential(self.features,
                                                                        len(self.features)//self.checkpoint,
                                                                        input)
            else:
                features = self.features(input)
            embedding = self.pool(features)
        if self.whitening is not None:
            embedding = self.whitening(embedding)
        classifier_input = embedding
        if self.pre_classifier is not None:
            classifier_input = self.pre_classifier(classifier_input)
        classifier_output = self.classifier(classifier_input)
        return embedding, classifier_output

