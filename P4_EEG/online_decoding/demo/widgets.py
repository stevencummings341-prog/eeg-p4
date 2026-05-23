"""widgets.py — MNE 地形图 Canvas"""

import matplotlib
matplotlib.use("QtAgg")

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import mne

import config


class MneTopoCanvas(FigureCanvas):
    """MNE 1020 蒙太奇头皮地形图"""

    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig, self.ax = plt.subplots(figsize=(width, height), dpi=dpi)
        self.fig.patch.set_facecolor("white")
        self.ax.axis("off")
        super().__init__(self.fig)
        self.setParent(parent)
        self.fig.tight_layout(pad=0)

        montage = mne.channels.make_standard_montage("standard_1020")
        self.info = mne.create_info(
            ch_names=config.CHANNEL_NAMES,
            sfreq=config.DEFAULT_SFREQ,
            ch_types="eeg",
        )
        self.info.set_montage(montage)

    def update_topo(self, data_vector):
        if len(data_vector) != len(config.CHANNEL_NAMES):
            return
        self.ax.clear()
        mne.viz.plot_topomap(
            data_vector, self.info, axes=self.ax,
            show=False, cmap="RdBu_r", contours=4,
            sensors=True, sphere="auto",
        )
        self.draw()
