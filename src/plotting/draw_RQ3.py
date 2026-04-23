import os
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np

# ======================
# 读取 CSV
# ======================
df = pd.read_csv(
    "/home/rs/WorkEx/Projects/SoftwareTesting/0ExperimentPlayGround/fxj/RQ3_EXAM_long.csv"
)

# ======================
# 全局字体设置
# ======================
plt.rcParams.update({
    "font.size": 24,
    "axes.labelsize": 24,
    "xtick.labelsize": 26,
    "ytick.labelsize": 24
})

# ======================
# 分组
# ======================
df["Group"] = df["Strategy"].apply(
    lambda x: "Major" if x.startswith("Major") else "μBERT"
)

# ======================
# 名称映射
# ======================
rename_map = {
    "Major + Soft Weighting": "SW",
    "Major + Hard Filtering (30%)": "HF (30%)",
    "Major + Hard Filtering (50%)": "HF (50%)",
    "Major + Hard Filtering (70%)": "HF (70%)",

    "μBERT + Soft Weighting": "SW",
    "μBERT + Hard Filtering (30%)": "HF (30%)",
    "μBERT + Hard Filtering (50%)": "HF (50%)",
    "μBERT + Hard Filtering (70%)": "HF (70%)"
}

df["Strategy"] = df["Strategy"].replace(rename_map)

# ======================
# 拆分数据
# ======================
df_major = df[df["Group"] == "Major"].copy()
df_μBERT = df[df["Group"] == "μBERT"].copy()

major_order = ["Major", "SW", "HF (30%)", "HF (50%)", "HF (70%)"]
μBERT_order = ["μBERT", "SW", "HF (30%)", "HF (50%)", "HF (70%)"]

# ======================
# 保存目录
# ======================
save_dir = "/home/rs/WorkEx/Projects/SoftwareTesting/0ExperimentPlayGround/fxj/figures/RQ3_box"
os.makedirs(save_dir, exist_ok=True)

# ======================
# 绘图函数（无底部标题）
# ======================
def draw_boxplot(data, order, colors, save_name):
    fig, ax = plt.subplots(figsize=(13, 6.6))

    bp = ax.boxplot(
        [data[data["Strategy"] == s]["EXAM"].values for s in order],
        labels=order,
        patch_artist=True,
        vert=False,
        widths=0.6,
        boxprops=dict(linewidth=1.5),
        medianprops=dict(linewidth=2.0, color="red"),
        whiskerprops=dict(linewidth=1.3),
        capprops=dict(linewidth=1.3)
    )

    # 颜色
    for i, patch in enumerate(bp["boxes"]):
        patch.set_facecolor(colors[i])
        patch.set_alpha(0.85)

    # 散点
    for i, strategy in enumerate(order):
        vals = data[data["Strategy"] == strategy]["EXAM"].values
        y_jitter = np.random.normal(i + 1, 0.04, size=len(vals))
        ax.scatter(vals, y_jitter, s=20, alpha=0.28, c="black")

    # baseline 中位线
    baseline = data[data["Strategy"] == order[0]]["EXAM"].median()
    ax.axvline(
        x=baseline,
        linestyle=":",
        color="gray",
        linewidth=1.8,
        alpha=0.8
    )

    # 坐标轴
    ax.set_xlabel("EXAM (lower is better)", fontsize=22, labelpad=10)
    ax.set_ylabel("")
    ax.set_xlim(0, 1)
    ax.grid(axis="x", linestyle="--", alpha=0.3)
    ax.invert_yaxis()

    ax.tick_params(axis="x", labelsize=26)
    ax.tick_params(axis="y", labelsize=24)

    sns.despine(left=True)

    plt.tight_layout()

    # 保存
    plt.savefig(
        os.path.join(save_dir, save_name + ".pdf"),
        dpi=300,
        bbox_inches="tight"
    )
    plt.savefig(
        os.path.join(save_dir, save_name + ".png"),
        dpi=300,
        bbox_inches="tight"
    )

    plt.show()


# ======================
# Major 图
# ======================
draw_boxplot(
    df_major,
    major_order,
    ['#1f77b4', '#4a9eda', '#74c7e8', '#9ed4f2', '#c8e1fa'],
    "RQ3_EXAM_Major"
)

# ======================
# μBERT 图
# ======================
draw_boxplot(
    df_μBERT,
    μBERT_order,
    ['#d95f02', '#e78c33', '#f2b065', '#f7cf97', '#fbe9c9'],
    "RQ3_EXAM_uBERT"
)