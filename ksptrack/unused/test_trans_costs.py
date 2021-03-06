from sklearn.metrics import (f1_score,roc_curve,auc,precision_recall_curve)
import glob
import warnings, itertools, _pickle, progressbar, sys, os, datetime, yaml, hashlib, json
from ksptrack.cfgs import cfg
from ksptrack.utils import learning_dataset
from ksptrack.utils import superpixel_utils as spix
from ksptrack import sp_manager as spm
from ksptrack.utils import csv_utils as csv
from ksptrack.utils import my_utils as utls
from ksptrack.utils.data_manager import DataManager 

import pandas as pd
import pickle as pk
import numpy as np
import matplotlib.pyplot as plt
import scipy.io
from scipy import ndimage
from skimage import (color, io, segmentation, draw)
import shutil as sh
import logging
from skimage import filters
import scipy as sp


def main(arg_cfg):
    data = dict()

    #Update config
    cfg_dict = cfg.cfg()
    arg_cfg['seq_type'] = cfg.datasetdir_to_type(arg_cfg['dataSetDir'])
    cfg_dict.update(arg_cfg)
    conf = cfg.dict_to_munch(cfg_dict)

    #Write config to result dir
    conf.dataOutDir = utls.getDataOutDir(conf.dataOutRoot, conf.dataSetDir, conf.resultDir,
                                    conf.fileOutPrefix, conf.testing)

    #Set logger
    utls.setup_logging(conf.dataOutDir)

    logger = logging.getLogger('iterative_ksp')


    logger.info('---------------------------')
    logger.info('starting experiment on: ' + conf.dataSetDir)
    logger.info('type of sequence: ' + conf.seq_type)
    logger.info('gaze filename: ' + conf.csvFileName_fg)
    logger.info('features type: ' + conf.feat_extr_algorithm)
    logger.info('Result dir:')
    logger.info(conf.dataOutDir)
    logger.info('---------------------------')

    #Make frame file names
    gt_dir = os.path.join(conf.dataInRoot, conf.dataSetDir, conf.gtFrameDir)
    gtFileNames = utls.makeFrameFileNames(
        conf.framePrefix, conf.frameDigits, conf.gtFrameDir,
        conf.dataInRoot, conf.dataSetDir, conf.frameExtension)

    conf.frameFileNames = utls.makeFrameFileNames(
        conf.framePrefix, conf.frameDigits, conf.frameDir,
        conf.dataInRoot, conf.dataSetDir, conf.frameExtension)


    conf.myGaze_fg = utls.readCsv(os.path.join(conf.dataInRoot,conf.dataSetDir,conf.gazeDir,conf.csvFileName_fg))


    if (conf.labelMatPath != ''):
        conf.labelMatPath = os.path.join(conf.dataOutRoot, conf.dataSetDir, conf.frameDir,
                                    conf.labelMatPath)

    conf.precomp_desc_path = os.path.join(conf.dataOutRoot, conf.dataSetDir,
                                    conf.feats_files_dir)

    # ---------- Descriptors/superpixel costs
    my_dataset = DataManager(conf)
    if(conf.calc_superpix): my_dataset.calc_superpix(save=True)

    my_dataset.load_superpix_from_file()
    #my_dataset.relabel(save=True,who=conf.relabel_who)

    from scipy.spatial.distance import mahalanobis
    from metric_learn import LFDA
    from sklearn.decomposition import PCA

    #Calculate covariance matrix
    descs = my_dataset.sp_desc_df
    labels = my_dataset.labels
    my_dataset.load_all_from_file()
    pm = my_dataset.fg_pm_df

    sps_man_for = spm.SuperpixelManager(my_dataset,
                                        conf,
                                        direction='forward',
                                        with_flow=True)
    sps_man_back = spm.SuperpixelManager(my_dataset,
                                        conf,
                                        direction='backward',
                                        with_flow=True)
    sps_man_for.make_dicts()
    sps_man_back.make_dicts()

    my_dataset.load_pm_fg_from_file()
    my_dataset.calc_pm(conf.myGaze_fg,
                       save=True,
                       marked_feats=None,
                       all_feats_df=my_dataset.get_sp_desc_from_file(),
                       in_type='csv_normalized',
                       mode='foreground',
                       feat_fields=['desc'])

    conf.myGaze_fg = utls.readCsv(os.path.join(conf.dataInRoot,
                                               conf.dataSetDir,
                                               conf.gazeDir,
                                               conf.csvFileName_fg))

    my_thresh = 0.8
    lfda_n_samps = 1000

    frame_1 = 1

    gaze_1 = conf.myGaze_fg[frame_1,3:5]
    g1_i, g1_j = utls.norm_to_pix(gaze_1[0],
                                  gaze_1[1],
                                  labels[...,0].shape[1],
                                  labels[...,0].shape[0])
    label_1 = labels[g1_i, g1_j, frame_1]

    frame_2 = 2

    pm_scores_fg = my_dataset.get_pm_array(mode='foreground', frames=[frame_2])

    df = descs.loc[descs['frame'] == frame_2]
    feat_1 = descs.loc[(descs['frame'] == frame_1) & (descs['sp_label'] == label_1),'desc'].as_matrix()[0]
    descs_from = [feat_1]*df.shape[0]
    df.loc[:,'descs_from'] = pd.Series(descs_from, index=df.index)
    descs_2 = utls.concat_arr(df['desc'].as_matrix())

    pm = my_dataset.fg_pm_df
    #y = (pm.loc[(pm['frame'] == frame_2),'proba'] > thresh_aux).as_matrix().astype(int)
    y = (pm['proba'] > my_thresh).as_matrix().astype(int)

    lfda = LFDA(dim=45, k=23)

    n_comps_pca = 3

    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.decomposition import PCA
    lda = LinearDiscriminantAnalysis(n_components=25)
    pca = PCA(n_components=n_comps_pca, whiten=True)

    descs_cat = utls.concat_arr(descs['desc'])
    rand_idx_pos = np.random.choice(np.where(y > 0)[0],size=lfda_n_samps)
    rand_idx_neg = np.random.choice(np.where(y == 0)[0],size=lfda_n_samps)
    descs_cat = utls.concat_arr(descs['desc'])
    rand_descs_pos = descs_cat[rand_idx_pos,:]
    rand_descs_neg = descs_cat[rand_idx_neg,:]
    rand_y_pos = y[rand_idx_pos]
    rand_y_neg = y[rand_idx_neg]
    rand_descs = np.concatenate((rand_descs_pos,rand_descs_neg),axis=0)
    rand_y = np.concatenate((rand_y_pos,rand_y_neg),axis=0)

    #lfda.fit(rand_descs, rand_y)
    #lda.fit(rand_descs, rand_y)
    pca.fit(descs_cat)

    #f1 = lfda.transform(feat_1)
    #f2 = lfda.transform(descs_2)
    #f1 = lda.transform(feat_1.reshape(1,-1))
    #f2 = lda.transform(descs_2)
    f1 = pca.transform(feat_1.reshape(1,-1))
    f2 = pca.transform(descs_2)
    diff_norm = np.linalg.norm(f2-np.tile(f1, (f2.shape[0],1)),axis=1)

    dists = np.zeros(labels[...,frame_2].shape)
    for l in np.unique(labels[...,frame_2]):
        dists[labels[...,frame_2]==l] = np.exp(-diff_norm[l]**2)
        #dists[labels[...,frame_2]==l] = -diff_norm[l]

    im1 = utls.imread(conf.frameFileNames[frame_1])
    label_cont = segmentation.find_boundaries(labels[...,frame_1], mode='thick')
    aimed_cont = segmentation.find_boundaries(labels[...,frame_1] == label_1,
                                              mode = 'thick')


    label_cont_im = np.zeros(im1.shape, dtype=np.uint8)
    label_cont_i, label_cont_j = np.where(label_cont)
    label_cont_im[label_cont_i,label_cont_j,:] = 255

    io.imsave('conts.png',label_cont_im)

    rr, cc = draw.circle_perimeter(g1_i,g1_j,
                                      int(conf.normNeighbor_in*im1.shape[1]))

    im1[rr,cc,0] = 0
    im1[rr,cc,1] = 255
    im1[rr,cc,2] = 0

    im1[aimed_cont,:] = (255,0,0)

    entr_labels_1 = []
    centroids = spix.getLabelCentroids(labels[...,frame_1][...,np.newaxis])
    #for l in np.unique(labels[...,frame_1]):
    #    centroid =

    im1 =  csv.draw2DPoint(conf.myGaze_fg,
                           frame_1,
                           im1,
                           radius=7)

    im2 = utls.imread(conf.frameFileNames[frame_2])
    label_cont = segmentation.find_boundaries(labels[...,frame_1], mode='thick')
    im2[label_cont,:] = (255,255,255)

    #plt.imshow(im1); plt.show()
    plt.subplot(321)
    plt.imshow(im1)
    plt.title('frame_1. ind: ' + str(frame_1))
    plt.subplot(322)
    plt.imshow(im2)
    plt.title('frame_2. ind: ' + str(frame_2))
    plt.subplot(323)
    plt.imshow(labels[...,frame_1])
    plt.title('labels frame_1')
    plt.subplot(324)
    plt.imshow(labels[...,frame_2])
    plt.title('labels frame_2')
    plt.subplot(325)
    plt.imshow(dists)
    plt.title('dists')
    plt.subplot(326)
    #plt.imshow(pm_scores_fg[...,frame_2] > my_thresh)
    plt.imshow(pm_scores_fg[...,frame_2])
    plt.title('f2. pm > thresh (' + str(my_thresh) + ')')
    plt.show()
    #plt.savefig('t1000.png')

    return conf
