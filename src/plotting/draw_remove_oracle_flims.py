# rq2_project_level_1x4_whitelist_advanced_fixed.py

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os
from scipy import stats

# ==============================
# 路径
# ==============================

csv_path = "/home/rs/WorkEx/Projects/SoftwareTesting/0ExperimentPlayGround/fxj/bfl_summary_oracle.csv"
output_dir = "/home/rs/WorkEx/Projects/SoftwareTesting/0ExperimentPlayGround/fxj/figures/RQ2_1x4_1"

os.makedirs(output_dir, exist_ok=True)

# ==============================
# Defects4J 17个项目（白名单）
# ==============================

REAL_PROJECTS = [
    'Chart', 'Closure', 'Lang', 'Math', 'Mockito', 'Time',
    'Cli', 'Codec', 'Collections', 'Compress', 'Csv',
    'Gson', 'JacksonCore', 'JacksonDatabind', 'JacksonXml',
    'Jsoup', 'JxPath'
]

# ==============================
# 高级论文风格配置
# ==============================

def set_paper_style():
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "font.size": 18,
        "axes.labelsize": 15,
        "axes.titlesize": 18,
        "legend.fontsize": 12,
        "xtick.labelsize": 16,
        "ytick.labelsize": 16,

        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.05,

        "lines.linewidth": 1.5,
        "lines.markersize": 8,
        "lines.markeredgewidth": 1,

        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linestyle": "--",

        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.axisbelow": True,

        "legend.frameon": True,
        "legend.framealpha": 0.9,
        "legend.edgecolor": "black",
        "legend.fancybox": False,

        "axes.prop_cycle": plt.cycler(color=['#2E86AB', '#A23B72', '#F18F01', '#C73E1D']),
    })

set_paper_style()

# ==============================
# 自定义颜色
# ==============================

COLOR_WITH = "#2E86AB"
COLOR_WITHOUT = "#A23B72"
COLOR_IMPROVE = "#2C8C5A"
COLOR_DECLINE = "#C73E1D"

# ==============================
# 数据读取和诊断
# ==============================

print("=" * 60)
print("数据诊断")
print("=" * 60)

df = pd.read_csv(csv_path)

df_filtered = df[
    (df['Granularity'] == 'Statement') &
    (df['Kill Type'] == 'Weak Kill') &
    (df['Formula'] == 'Ochiai')
]

major_with = df_filtered[df_filtered['Mutation Method'] == 'major']
major_without = df_filtered[df_filtered['Mutation Method'] == 'major_flim_oracle']
mbert_with = df_filtered[df_filtered['Mutation Method'] == 'mBERT']
mbert_without = df_filtered[df_filtered['Mutation Method'] == 'mBERT_flim_oracle']

# ==============================
# 统计检验函数
# ==============================

def wilcoxon_test(data_with, data_without):
    try:
        statistic, p_value = stats.wilcoxon(data_with, data_without)
        return p_value
    except:
        return None

# ==============================
# 绘图函数（仅修 legend）
# ==============================
def create_1x4_plot(df_with, df_without, method_name):
    projects = [p for p in REAL_PROJECTS if p in set(df_with['Project']) and p in set(df_without['Project'])]
    if len(projects) == 0:
        return

    data = []
    for p in projects:
        w = df_with[df_with['Project'] == p].iloc[0]
        wo = df_without[df_without['Project'] == p].iloc[0]
        data.append({
            'project': p,
            'with_MFR': w['MFR'],
            'without_MFR': wo['MFR'],
            'with_MAP': w['MAP'],
            'without_MAP': wo['MAP'],
            'with_top1': w['top1'],
            'without_top1': wo['top1'],
            'with_top3': w['top3'],
            'without_top3': wo['top3'],
        })

    dfp = pd.DataFrame(data)
    x = np.arange(len(projects))

    fig, axes = plt.subplots(1, 4, figsize=(24, 5), constrained_layout=True)

    metrics = [
        ('MFR', 'with_MFR', 'without_MFR'),
        ('MAP', 'with_MAP', 'without_MAP'),
        ('Top-1', 'with_top1', 'without_top1'),
        ('Top-3', 'with_top3', 'without_top3')
    ]

    for idx, (ylabel, col_w, col_wo) in enumerate(metrics):
        ax = axes[idx]

        ax.scatter(x-0.1, dfp[col_w], color='dodgerblue', s=70, label='With FLIMs', edgecolors='k')
        ax.scatter(x+0.1, dfp[col_wo], color='orange', s=70, label='Without FLIMs', edgecolors='k')

        for i, (w, wo) in enumerate(zip(dfp[col_w], dfp[col_wo])):
            if ylabel == 'MFR':
                color = 'green' if wo < w else 'red'
            else:
                color = 'green' if wo > w else 'red'
            ax.plot([i-0.1, i+0.1], [w, wo], color=color, alpha=0.6, linewidth=2)

        ax.axhline(dfp[col_w].mean(), linestyle='--', color='dodgerblue', alpha=0.6)
        ax.axhline(dfp[col_wo].mean(), linestyle='--', color='orange', alpha=0.6)

        # ❌ 删除子图标题（关键修改）
        # ax.set_title(...)

        ax.set_ylabel(ylabel)
        ax.set_xticks(x)
        ax.set_xticklabels(projects, rotation=45, ha='right')
        ax.grid(alpha=0.2, linestyle='--')

    # ======================
    # legend（保留一个）
    # ======================
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc='lower center',
        ncol=2,
        bbox_to_anchor=(0.5, -0.08)
    )

    # 给底部留空间（防止 legend 被挤）
    plt.subplots_adjust(bottom=0.25, top=0.92)

    # 总标题
    # if method_name == 'Major':
    #     method_class = 'Traditional Mutation'
    # else:
    #     method_class = 'Neural Mutation'
    method_class = ' '

    fig.suptitle(method_class, fontsize=16, fontweight='bold')

    save_path = os.path.join(output_dir, f'{method_name}_clean.png')
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
# ==============================
# 执行
# ==============================

if __name__ == "__main__":
    create_1x4_plot(major_with, major_without, 'Major')
    create_1x4_plot(mbert_with, mbert_without, 'mBERT')