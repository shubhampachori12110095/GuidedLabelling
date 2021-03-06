#!/usr/bin/env python

__author__ = 'joon'

import sys

sys.path.insert(0, 'src')
sys.path.insert(0, 'lib')
sys.path.insert(0, 'ResearchTools')

from imports.basic_modules import *
from imports.import_caffe import *
from imports.ResearchTools import *
from imports.libmodules import *

from config import config_test
from networks import gap

####

EXP_PHASE = 'seed-test'

conf = dict(
    save_cls=True,
    save_heat=True,
    vis=False,
    visconf=0.2,
    shuffle=True,
    overridecache=True,
    pascalroot="/BS/joon_projects/work/",
    imagenetmeanloc="data/ilsvrc_2012_mean.npy",
    gpu=1,
)

control = dict(
    init='VGG_ILSVRC_16_layers',
    net='GAP-HighRes',
    dataset='voc12train_aug',
    datatype='Segmentation',
    base_lr=0.001,
    batch_size=15,
    balbatch='clsbal',
    test_iter=8000,
    test_dataset='voc12train_aug',
    test_datatype='Segmentation',
    test_ranking='none',
    test_interpord=1,
    test_gtcls='use',
)


####

def parse_input(argv=sys.argv):
    parser = argparse.ArgumentParser(description="Tests a seed network")
    parser.add_argument('--init', default='VGG_ILSVRC_16_layers', type=str,
                        help='Initialisation for the network')
    parser.add_argument('--net', default='GAP-HighRes', type=str,
                        help='Network')
    parser.add_argument('--dataset', default='voc12train_aug', type=str,
                        help='Training set')
    parser.add_argument('--datatype', default='Segmentation', type=str,
                        help='Type of training set')
    parser.add_argument('--base_lr', default=0.001, type=float,
                        help='Base learning rate')
    parser.add_argument('--batch_size', default=15, type=int,
                        help='Batch size')
    parser.add_argument('--balbatch', default='clsbal', type=str,
                        help='Class balanced batch composition')
    parser.add_argument('--test_iter', default=8000, type=int,
                        help='Test model iteration')
    parser.add_argument('--test_dataset', default='voc12val', type=str,
                        help='Test dataset')
    parser.add_argument('--test_datatype', default='Segmentation', type=str,
                        help='Type of test data')
    parser.add_argument('--test_ranking', default='none', type=str,
                        help='When testing, dont rank priority according to size @ 20 percent max score as in lamperts')
    parser.add_argument('--test_interpord', default=1, type=int,
                        help='Interpolation order')
    parser.add_argument('--test_gtcls', default='use', type=str,
                        help='Use GT class information at test time')
    control = vars(parser.parse_known_args(argv)[0])

    parser_conf = argparse.ArgumentParser()
    parser_conf.add_argument('--pascalroot', default='/home', type=str,
                             help='Pascal VOC root folder')
    parser_conf.add_argument('--imagenetmeanloc', default='/home', type=str,
                             help='Imagenet mean image location')
    parser_conf.add_argument('--gpu', default=1, type=int,
                             help='GPU ID')
    parser_conf.add_argument('--vis', default=False, type=bool,
                             help='Visualisation')
    parser_conf.add_argument('--visconf', default=0.5, type=float,
                             help='Visualisation seed threshold')
    parser_conf.add_argument('--save_cls', default=True, type=bool,
                             help='Save class prediction')
    parser_conf.add_argument('--save_heat', default=True, type=bool,
                             help='Save raw heatmap output')
    parser_conf.add_argument('--overridecache', default=True, type=bool,
                             help='Override cache')
    parser_conf.add_argument('--shuffle', default=True, type=bool,
                             help='Shuffle test input order')
    conf = vars(parser_conf.parse_known_args(argv)[0])
    return control, conf


def write_proto(testproto, conf, control):
    f = open(testproto, 'w')
    f.write(gap(conf, control, 'test'))
    f.close()
    return


def setup_net(control, control_model, control_token, conf):
    # prototxt
    protodir = osp.join('models', EXP_PHASE, create_token(control_token))
    mkdir_if_missing(protodir)
    testproto = osp.join(protodir, 'test.prototxt')
    write_proto(testproto, conf, control)

    learnedmodel_dir = osp.join('cache', 'seed-train', create_token(control_model))
    learnedmodel = osp.join(learnedmodel_dir, '_iter_' + str(control['test_iter']) + '.caffemodel')

    # init
    caffe.set_mode_gpu()
    caffe.set_device(conf['gpu'])

    net = caffe.Net(testproto, learnedmodel, caffe.TEST)
    disp_net(net)

    return net


def compute_out_heat(net, gt_cls, conf):
    CAM_scores = net.blobs[conf['blobname_map']].data[0]
    params = net.params[conf['paramname_weight']][0].data[...]

    osz = conf['out_size']

    heat_maps = np.zeros((len(gt_cls), osz, osz))
    for idx, cls in enumerate(gt_cls):
        i = int(cls - 1)
        w = params[i]
        heat_maps[idx, :, :] = np.sum(CAM_scores * w[:, None, None], axis=0)

    return heat_maps


def run_test(net, out_dir, control, conf):
    year = '20' + control['test_dataset'][3:5]
    pascal_list = get_pascal_indexlist(conf['pascalroot'], year, control['test_datatype'], control['test_dataset'][5:],
                                       shuffle=conf['shuffle'])

    num_test = len(pascal_list)
    print('%d images for testing' % num_test)

    transformer = set_preprocessor_without_net(
        [1, 3, conf['input_size'], conf['input_size']],
        mean_image=np.load(conf['imagenetmeanloc']).mean(1).mean(1))

    pred_list = []
    id_list = []

    start_time = time.time()
    for idx in range(num_test):
        end_time = time.time()
        print ('    Iter %d took %2.1f seconds' % (idx, end_time - start_time))
        start_time = time.time()
        print ('    Running %d out of %d images' % (idx + 1, num_test))

        inst = idx
        im_id = pascal_list[inst]
        outfile = osp.join(out_dir, im_id + '.mat')

        if conf['save_heat']:
            if not conf['overridecache']:
                if osp.isfile(outfile):
                    print('skipping')
                    continue

        gtfile = conf['clsimgpath'] % (im_id)
        gt = np.array(Image.open(gtfile)).astype(np.float)
        gt_cls = np.unique(gt)
        gt_cls_nobg = gt_cls[(gt_cls != 0) & (gt_cls != 255)]

        imloc = os.path.join(conf['pascalroot'], 'VOC' + year, 'JPEGImages', im_id + '.jpg')
        image = load_image_PIL(imloc)
        imshape_original = image.shape[:2]

        net.blobs[conf['inputname']].data[...][0], confs_process = preprocess_convnet_image(image, transformer, 321,
                                                                                            'test',
                                                                                            return_deprocess_confs=True)
        net.forward()

        heat_maps = compute_out_heat(net, gt_cls_nobg, conf)
        heat_maps = deprocess_convnet_label(heat_maps, confs_process, order=control['test_interpord'])

        cls_preds = net.blobs[conf['outputname']].data[0, :]

        pred_list.append(cls_preds.copy())
        id_list.append(im_id)

        if conf['vis']:
            seg, confidence = heatmap2segconf(heat_maps, imshape_original, gt_cls_nobg)

            def visualise_data():
                fig = plt.figure(0, figsize=(15, 10))
                fig.suptitle('ID:{}'.format(im_id))
                ax = fig.add_subplot(1, 2, 1)
                ax.set_title('Original image')
                pim(image)

                ax = fig.add_subplot(2, 4, 3)
                ax.set_title('FG class prediction')
                ax.imshow(seg, cmap="nipy_spectral", clim=(0, 30))
                ax = fig.add_subplot(2, 4, 7)
                ax.imshow(image)
                ax.imshow(seg, alpha=.5, cmap="nipy_spectral", clim=(0, 30))

                ax = fig.add_subplot(2, 4, 4)
                ax.set_title('Seed: heatmap thresholded @' + str(conf['visconf']))
                ax.imshow(seg * (confidence > conf['visconf']), cmap="nipy_spectral", clim=(0, 30))
                ax = fig.add_subplot(2, 4, 8)
                ax.imshow(image)
                ax.imshow(seg * (confidence > conf['visconf']), alpha=.5, cmap="nipy_spectral", clim=(0, 30))

                for iii in range(5):
                    fig.axes[iii].get_xaxis().set_visible(False)
                    fig.axes[iii].get_yaxis().set_visible(False)

                plt.pause(1)
                return

            visualise_data()

        if conf['save_heat']:
            if not conf['overridecache']:
                assert (not os.path.isfile(outfile))
            else:
                if os.path.isfile(outfile):
                    print('WARNING: OVERRIDING EXISTING RESULT FILE')
            sio.savemat(outfile, dict(heatmap=heat_maps, imshape_original=imshape_original))
            print('results saved to %s' % outfile)

    if conf['save_cls']:
        outfile_cls = osp.join(out_dir, 'cls_res.mat')
        pred_cls = np.vstack(pred_list)
        sio.savemat(outfile_cls, dict(res=pred_cls, ids=id_list))
        print('results saved to %s' % outfile_cls)

    return


def main(control, conf):
    control, control_model, control_token, conf = config_test(control, conf, EXP_PHASE)

    out_dir = osp.join('cache', EXP_PHASE, create_token(control_token))
    mkdir_if_missing(out_dir)
    print('saving to: {}'.format(out_dir))

    net = setup_net(control, control_model, control_token, conf)

    run_test(net, out_dir, control, conf)
    return


if __name__ == '__main__':
    if len(sys.argv) != 1:
        control, conf = parse_input(sys.argv)
    main(control, conf)
