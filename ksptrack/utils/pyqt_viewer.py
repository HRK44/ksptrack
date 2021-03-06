import scipy.io as io
import pyqtgraph as pg
import numpy as np
from pyqtgraph.Qt import QtCore, QtGui
from skimage.draw import (circle,set_color)
from skimage import color
from skimage.io import imsave
from skimage import transform
import csv
import sys, getopt
import os.path
from ksptrack.utils import csv_utils as csv
from ksptrack.utils import my_utils as utls
import natsort
import glob

def isKeyPressed(gaze,frameNum):
    return bool(gaze[frameNum,2])

class SliderWithText(QtGui.QWidget):
    def __init__(self, *var, **kw):
        QtGui.QWidget.__init__(self, *var, **kw)
        self.slider = QtGui.QSlider()
        self.slider.setOrientation(QtCore.Qt.Horizontal)
        self.label = QtGui.QLabel(self)
        # QVBoxLayout the label above; could use QHBoxLayout for
        # side-by-side
        layout = QtGui.QVBoxLayout()
        #layout.setMargin(0)
        layout.setSpacing(2)
        layout.addWidget(self.label)
        layout.addWidget(self.slider)
        self.setLayout(layout)
        #self.style_off = '<span style=" font-size:8pt; font-weight:600; color:#aa0000;">'
        #self.style_on = '<span style=" font-size:8pt; font-weight:600; color:#00aa00;">'
    def set_text(self,string,mode):
        if(mode): #Display on style
            self.label.setStyleSheet("font-weight: bold; color: green");
            #self.label.setText(self.style_on + string + '</span>')
            self.label.setText(string)
        else: #Display off style
            self.label.setStyleSheet("font-weight: bold; color: red");
            #self.label.setText(self.style_off + string + '</span>')
            self.label.setText(string)


class Window(QtGui.QMainWindow):
    def __init__(self,
                 frame_dir,
                 frames,
                 gts,
                 dir_clicks,
                 gaze_array=None,
                 label_contours=None,
                 labels=None,
                 parent=None,
                 remove_duplicate_clicks=True):
    #my_window = Window(frame_dir,sorted_frames,sorted_gt,dir_clicks,gaze_,labelContourMask)
        super(Window, self).__init__(parent)
        self.setWindowTitle('Mes jolies images')
        self.window = pg.ImageView(view=pg.PlotItem())
        self.slider_text = SliderWithText()
        self.label_contours = label_contours
        self.labels = labels
        self.remove_duplicate_clicks = remove_duplicate_clicks

        self.setCentralWidget(self.window)
        self.slider_text.slider.setMinimum(1)
        self.slider_text.slider.setMaximum(len(frames))
        self.slider_text.slider.setTickInterval(1)
        self.slider_text.slider.setSingleStep(1)

        self.label = QtGui.QLabel(self)
        #self.label.setGeometry(160, 40, 80, 30)

        self.frames = frames
        self.frame_dir = frame_dir
        self.gts = gts
        self.dir_clicks = dir_clicks

        self.curr_img = utls.imread(os.path.join(self.frame_dir,self.frames[0]))
        self.gaze_ = gaze_array
        self.mouse_clicks = []
        self.labels_clicked = []

        # add the menubar with the method createMenuBar()
        self.createMenuBar()
        # add the dock widget with the method createDockWidget()
        self.createDockWidget()
        #
        # first set the default value to a
        self.curr_idx = 0
        self.max_idx = len(self.frames)
        self.slider_text.slider.setValue(self.curr_idx)
        self.drawFrame(self.curr_idx)

        self.sliderValueChanged(0)
        string = "Frame " + str(self.curr_idx + 1) + "/" + str(len(self.frames))

        self.slider_text.set_text(string,self.is_already_clicked(self.curr_idx))
        self.slider_text.slider.valueChanged.connect(self.sliderValueChanged)


    def is_already_clicked(self,idx):
        if(len(self.mouse_clicks) > 0):
            if(self.curr_idx in np.asarray(self.mouse_clicks)[:,0]):
                return True
            else:
                return False
        else:
            return False

    def keyPressEvent(self,event):

        if event.key() == QtCore.Qt.Key_A:
            #print("pressed A")
            if(self.curr_idx < len(self.frames)-1):
                #self.curr_idx += 1
                self.sliderValueChanged(self.curr_idx+1)
        if event.key() == QtCore.Qt.Key_S:
            #print("pressed S")
            if(self.curr_idx > 0):
                #self.curr_idx -= 1
                self.sliderValueChanged(self.curr_idx-1)

    def on_click(self,event):
        x = event.pos().x()
        y = event.pos().y()
        im_shape = self.curr_img.shape
        x_norm,y_norm = csv.pix2Norm(x,y,im_shape[1], im_shape[0])
        print("(idx, x,y): ({}, {}, {})".format(self.curr_idx, x_norm, y_norm))
        self.mouse_clicks.append([self.curr_idx,0,1,x_norm,y_norm]) #frame,time,visible,x,y

        #Draw superpixel if exists
        if(self.labels is not None):
            self.update_clicked_labels(x,y)

    def update_clicked_labels(self,x,y):

        if(self.labels_clicked is not None):

            this_label = self.labels[int(y),int(x),self.curr_idx]
            #Already exist?
            if(this_label in self.labels_clicked):
                #Removes clicked label if it already exist
                print('label already tracked... removing it')
                self.labels_clicked = [self.labels_clicked[i] for i in range(len(self.labels_clicked)) if(self.labels_clicked[i] != this_label)]
                print(self.labels_clicked)
                self.sliderValueChanged(self.curr_idx)
                self.drawFrame(self.curr_idx)
            else:
                #Add it
                print('Adding label to track list')
                #self.labels_clicked.append((y,x))
                self.labels_clicked.append(this_label)
                print(self.labels_clicked)
                self.sliderValueChanged(self.curr_idx)
                self.drawFrame(self.curr_idx)


    def write_click_csv(self,n_frames):

        n_clicks_per_frame = [0 for i in range(len(n_frames))]
        #Populate click_arr
        for i in range(len(self.mouse_clicks)):
            n_clicks_per_frame[self.mouse_clicks[i][0]] += 1

        print('n_clicks_per_frame')
        print(n_clicks_per_frame)

        doubles = [i for i in range(len(n_clicks_per_frame))
                   if (n_clicks_per_frame[i] > 1)]
        print('doubles')
        print(doubles)


        if(self.remove_duplicate_clicks == True):
            rows_to_delete = []
            for i in range(len(doubles)):
                f = doubles[i]
                double_rows_idx = [i
                                for i in range(len(self.mouse_clicks))
                                if (self.mouse_clicks[i][0] == f)]
                rows_to_delete.append([double_rows_idx[i]
                                    for i in range(len(double_rows_idx)-1)])

            rows_to_delete = [item for sublist in rows_to_delete
                            for item in sublist]

            print('mouse_clicks')
            print(self.mouse_clicks)

            print('rows_to_delete')
            print(rows_to_delete)

            self.mouse_clicks = [self.mouse_clicks[i]
                                for i in range(len(self.mouse_clicks))
                                if(i not in rows_to_delete)]

            print('new mouse_clicks')
            print(self.mouse_clicks)

        click_arr = np.asarray(self.mouse_clicks)

        my_header = "VideoWidth:" + str(self.curr_img.shape[1]) + "\nVideoHeight:" + str(self.curr_img.shape[0]) + "\nDisplayWidth:0" + "\nDisplayHeight:0" + "\nframe;time;visible;x;y"

        file_out = os.path.join(self.dir_clicks,"video1.csv")

        print('[>>>] clicks doubled:')
        for i in range(len(self.frames)):
            if(np.where(click_arr[:,0] == i)[0].size > 1):
                print(i)
        print('[>>>] clicks missing:')
        for i in range(len(self.frames)):
            if(np.where(click_arr[:,0] == i)[0].size == 0):
                print(i)

        idx_sort = np.argsort(click_arr[:,0])
        click_arr = click_arr[idx_sort,:]

        print("Writing mouse clicks to: " + file_out)
        np.savetxt(file_out,
                   click_arr, delimiter=";",header=my_header,comments="",
                   fmt= ['%i','%i','%i', '%06f', '%06f'] )

        print("...done")

    def closeEvent(self, evnt):
        self.write_click_csv(self.frames)

    def sliderValueChanged(self, int_value):

        self.curr_idx = int_value

        string_to_disp = ''
        string_to_disp += "Frame " + str(int_value+1) + "/" + str(len(self.frames))

        if(self.gaze_ is not None):
            x = self.gaze_[self.curr_idx,3]
            y = self.gaze_[self.curr_idx,4]
            i,j = gaze.gazeCoord2Pixel(x,y,self.curr_img.shape[1],self.curr_img.shape[0])
            string_to_disp += ". gaze coordinate: (i,j) = (" + str(i) + "," + str(j) + ")"
            string_to_disp += ". gaze coordinate normalized: (y,x) = (" + str(y) + "," + str(x) + ")"

        string_to_disp += ". Clicked labels: " + str(self.labels_clicked)
        self.slider_text.set_text(string_to_disp,self.is_already_clicked(self.curr_idx))

        self.drawFrame(self.curr_idx)

    def createMenuBar(self):
        # file menu actions
        exit_action = QtGui.QAction('&Exit', self)
        exit_action.triggered.connect(self.close)
        # create an instance of menu bar
        menubar = self.menuBar()
        # add file menu and file menu actions
        file_menu = menubar.addMenu('&File')
        file_menu.addAction(exit_action)

    def createDockWidget(self):
        my_dock_widget = QtGui.QDockWidget()
        my_dock_widget.setObjectName('Control Panel')
        my_dock_widget.setAllowedAreas(QtCore.Qt.TopDockWidgetArea | QtCore.Qt.BottomDockWidgetArea)
        # create a widget to house user control widgets like sliders
        my_house_widget = QtGui.QWidget()
        # every widget should have a layout, right?
        my_house_layout = QtGui.QVBoxLayout()
        # add the slider initialized in __init__() to the layout
        my_house_layout.addWidget(self.slider_text)
        # apply the 'house' layout to the 'house' widget
        my_house_widget.setLayout(my_house_layout)
        # set the house widget 'inside' the dock widget
        my_dock_widget.setWidget(my_house_widget)
        # now add the dock widget to the main window
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, my_dock_widget)

    def drawFrame(self,idx):
        print('drawFrame')
        img = utls.imread(self.frames[idx])
        if(img.shape[2] > 3): img = img[:,:,0:3]
        if(self.label_contours is not None):
            idx_contours = np.where(self.label_contours[idx,:,:])
            img[idx_contours[0],idx_contours[1],:] = (255,255,255)

        if(self.gts is not None):
            gt = color.rgb2gray(utls.imread(self.gts[idx]))>0

        if(len(self.mouse_clicks) > 0):
            img = csv.draw2DPoint(np.asarray(self.mouse_clicks),
                                  idx,img,radius=7)
        if(self.gts is not None):
            img = color.label2rgb(gt,img,alpha=0.1)

        #Draw set of tracked labels
        if((self.labels is not None) & (len(self.labels_clicked) > 0)):

            #print(self.curr_idx)
            clicked_mask = np.zeros(self.labels[:,:,0].shape)
            for i in range(len(self.labels_clicked)):
                this_label = self.labels_clicked[i]
                clicked_mask += self.labels[:,:,self.curr_idx] == this_label
            img = color.label2rgb(clicked_mask,img,alpha=0.1)

        #print(img.shape)
        img = np.rot90(img)[::-1,:,:]
        self.window.setImage(img)

    def eventFilter(self, source, event):
        if event.type() == QtCore.QEvent.MouseMove:
            pos = event.pos()
            print(pos)
            #self.edit.setText('x: %d, y: %d' % (pos.x(), pos.y()))
        return QtGui.QMainWindow.eventFilter(self, source, event)

def main():
    app = QtGui.QApplication(sys.argv)
    app.setApplicationName('Image Viewer')

    #Get frame file names
    csvFileNum = 1
    dataset_dir = 'Dataset04'
    frame_dir = os.path.expanduser(os.path.join('/home/laurent.lejeune',
                                                'medical-labeling',
                                                dataset_dir,
                                                'input-frames'))
    #gt_dir = os.path.expanduser(os.path.join('/home/laurent.lejeune',
    #                                         'medical-labeling',
    #                                         dataset_dir,
    #                                         'ground_truth-frames'))
    #gazeFileName = 'video' + str(csvFileNum) + '.csv'
    #gazeFileName = 'framePositions' + str(csvFileNum) + '.csv'
    #csvFile = os.path.expanduser(os.path.join('~',
    #                                          'medical-labeling',
    #                                          dataset_dir,
    #                                          'gaze-measurements',
    #                                          gazeFileName))

    dir_clicks = os.path.join('.')

    sorted_frames = sorted(glob.glob(os.path.join(frame_dir,'*.png')))



    #Tweezer
    label_fname = 'sp_labels_tsp'

    labelContourMask = None #Won't show superpixels

    labels = None

    gaze_ = None

    my_window = Window(frame_dir,
                       sorted_frames,
                       None,
                       dir_clicks,
                       gaze_,
                       labelContourMask,
                       labels,
                       remove_duplicate_clicks = False)

    #Make event on click
    my_window.window.getImageItem().mousePressEvent = my_window.on_click

    #Mouse move coordinates
    #app.installEventFilter(my_window)

    my_window.show()
    app.exec_()

if __name__ == '__main__':
    main()
