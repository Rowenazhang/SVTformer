import argparse
import os
import math
import time
import torch
import sys


class opts():
    def __init__(self):
        self.parser = argparse.ArgumentParser()

    def init(self):

        self.parser.add_argument('--dataset', type=str, default='h36m', help='datset h36m||3dhp||SKI')
        self.parser.add_argument('-k', '--keypoints', default='cpn_ft_h36m_dbb', type=str, help='cpn_ft_h36m_dbb |gt')
        self.parser.add_argument('--data_augmentation', type=bool, default=True)
        self.parser.add_argument('--reverse_augmentation', type=bool, default=False)
        self.parser.add_argument('--test_augmentation', type=bool, default=True)
        self.parser.add_argument('--crop_uv', type=int, default=0)
        self.parser.add_argument('--root_path', type=str, default='dataset/')
        self.parser.add_argument('-a', '--actions', default='*', type=str)
        self.parser.add_argument('--downsample', default=1, type=int)
        self.parser.add_argument('--subset', default=1, type=float)
        self.parser.add_argument('-s', '--stride', default=1, type=int)
        self.parser.add_argument('--gpu', default='0', type=str, help='')
        self.parser.add_argument('--train', default=1)
        self.parser.add_argument('--test', action='store_true')
        self.parser.add_argument('--nepoch', type=int, default=50)
        self.parser.add_argument('--batch_size', type=int, default=32, help='can be changed depending on your machine')
        self.parser.add_argument('--lr', type=float, default=2e-4)
        self.parser.add_argument('--lr_decay_large', type=float, default=0.98)
        self.parser.add_argument('--large_decay_epoch', type=int, default=5)
        self.parser.add_argument('--workers', type=int, default=8)
        self.parser.add_argument('-lrd', '--lr_decay', default=0.98, type=float)
        self.parser.add_argument('--frames', type=int, default=27)
        self.parser.add_argument('--pad', type=int, default=175)
        self.parser.add_argument('--checkpoint', type=str, default='')
        self.parser.add_argument('--previous_dir', type=str, default='')
        self.parser.add_argument('--n_joints', type=int, default=17)
        self.parser.add_argument('--out_joints', type=int, default=17)
        self.parser.add_argument('--out_all', type=int, default=1)
        self.parser.add_argument('--in_channels', type=int, default=2)
        self.parser.add_argument('--out_channels', type=int, default=3)
        self.parser.add_argument('-previous_best_threshold', type=float, default=math.inf)
        self.parser.add_argument('-previous_name', type=str, default='')
        self.parser.add_argument('--model', default='', type=str)
        self.parser.add_argument('--depth', type=int, default=4)
        self.parser.add_argument('--embed_dim_ratio', type=int, default=32)

    def parse(self):
        self.init()

        self.opt = self.parser.parse_args()

        if self.opt.test:
            self.opt.train = 0

        self.opt.pad = (self.opt.frames - 1) // 2

        self.opt.subjects_train = 'S1,S5,S6,S7,S8'
        self.opt.subjects_test = 'S9,S11'

        if self.opt.train:
            logtime = time.strftime('%m%d_%H%M_%S_')
            self.opt.checkpoint = 'checkpoint/' + logtime + '%d' % (self.opt.frames) + '_' + self.opt.model
            if self.opt.dataset.startswith('3dhp'):
                self.opt.checkpoint += '_' + str(self.opt.dataset)
            self.opt.checkpoint += '_' + '%.6f'%(self.opt.lr) + '_' + '%d'%(self.opt.batch_size)
            if not torch.__version__.startswith('1.7'):
                self.opt.checkpoint += '_torch_' + str(torch.__version__)
            if not (sys.version_info.major == 3 and sys.version_info.minor == 7):
                self.opt.checkpoint += '_python_' + str(sys.version_info.major) + '.' + str(sys.version_info.minor)
            if not os.path.exists(self.opt.checkpoint):
                os.makedirs(self.opt.checkpoint)

            args = dict((name, getattr(self.opt, name)) for name in dir(self.opt)
                        if not name.startswith('_'))
            file_name = os.path.join(self.opt.checkpoint, 'opt.txt')
            with open(file_name, 'wt') as opt_file:
                opt_file.write('==> Args:\n')
                for k, v in sorted(args.items()):
                    opt_file.write('  %s: %s\n' % (str(k), str(v)))
                opt_file.write('==> Args:\n')

        return self.opt
