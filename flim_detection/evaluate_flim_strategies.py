import os
import pandas as pd
import numpy as np
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix
)

# =========================================================
# ====================== 参数区 ===========================
# =========================================================

# mutation_type: "traditional" | "mbert"
MUTATION_TYPE = "mbert"

#是否全局整体跑一个最佳θ
RUN_GLOBAL_THETA = False

# 是否只跑单个项目
SINGLE_PROJECT = False
TARGET_PROJECT = "Chart"

# θ 搜索步长
THETA_STEP = 0.05

# =========================================================
# ====================== 路径配置 =========================
# =========================================================

if MUTATION_TYPE == "traditional":
    FULL_CSV_ROOT = (
        "/home/rs/WorkEx/Projects/SoftwareTesting/MutationAnalysis/"
        "FLIMRecognitionResult/TraditionalMutation/major/"
        "Defects4J/D4JCleanCD4J/FLIMRecognition4FaultFile_full_added_csv"
    )
    OUTPUT_ROOT = (
        "/home/rs/WorkEx/Projects/SoftwareTesting/MutationAnalysis/"
        "FLIMRecognitionResult/TraditionalMutation/major/"
        "Defects4J/D4JCleanCD4J/FLIM_Evaluation_added"
    )
elif MUTATION_TYPE == "mbert":
    FULL_CSV_ROOT = (
        "/home/rs/WorkEx/Projects/SoftwareTesting/MutationAnalysis/"
        "FLIMRecognitionResult/NeuralMutation/mBERT/"
        "Defects4J/D4JCleanCD4J/FLIMRecognition4FaultFile_full_added_csv"
    )
    OUTPUT_ROOT = (
        "/home/rs/WorkEx/Projects/SoftwareTesting/MutationAnalysis/"
        "FLIMRecognitionResult/NeuralMutation/mBERT/"
        "Defects4J/D4JCleanCD4J/FLIM_Evaluation_added"
    )
else:
    raise ValueError(MUTATION_TYPE)

os.makedirs(OUTPUT_ROOT, exist_ok=True)

# =========================================================
# ====================== Stage 0 ==========================
# 递归读取所有 CSV
# =========================================================

def load_all_records():
    dfs = []

    for root, _, files in os.walk(FULL_CSV_ROOT):
        for file in files:
            if not file.endswith(".csv"):
                continue

            csv_path = os.path.join(root, file)
            try:
                df = pd.read_csv(csv_path)

                # 单项目过滤
                if SINGLE_PROJECT:
                    if "project" not in df.columns:
                        continue
                    df = df[df["project"] == TARGET_PROJECT]

                if len(df) > 0:
                    dfs.append(df)

            except Exception as e:
                print(f"[WARN] Failed to read {csv_path}: {e}")

    if not dfs:
        raise RuntimeError(f"[FATAL] No CSV files loaded from {FULL_CSV_ROOT}")

    all_df = pd.concat(dfs, ignore_index=True)
    print(f"[INFO] Loaded {len(all_df)} inference records")
    return all_df

# =========================================================
# ====================== Stage 1 ==========================
# mutant-level 聚合
# =========================================================


def aggregate_to_mutant_level(df):
    grouped = df.groupby(
        ["project", "version", "mutant_id"],
        as_index=False
    ).agg(
        y_true=("is_flim", "first"),
        n_preds=("pred_flim", "count"),
        flim_ratio=("pred_flim", "mean"),
        Sus=("Sus", "max")   
    )
    return grouped

# =========================================================
# ====================== Stage 2 ==========================
# θ 枚举 & 指标计算
# =========================================================

def evaluate_theta(mutant_df, theta):
    y_true = mutant_df["y_true"].astype(int)
    y_pred = (mutant_df["flim_ratio"] > theta).astype(int)

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()

    auc = None
    if len(np.unique(y_true)) > 1:
        auc = roc_auc_score(y_true, y_pred)

    return {
        "theta": theta,
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "auc": auc,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "real_flim": int(y_true.sum()),
        "pred_flim": int(y_pred.sum()),
    }

# =========================================================
# ====================== θ 选择逻辑 =======================
# =========================================================

def select_best_theta(results_df):
    # Step1: 找 precision 最大的所有行
    max_prec = results_df["precision"].max()
    prec_best = results_df[results_df["precision"] == max_prec]

    # Step2: 在 precision 最大行里找 auc 最大（如果有有效 AUC）
    if prec_best["auc"].notna().any():
        max_auc = prec_best["auc"].max()
        final_best = prec_best[prec_best["auc"] == max_auc].iloc[0]
    else:
        final_best = prec_best.iloc[0]

    return final_best

# =========================================================
# ====================== 主流程 ===========================
# =========================================================

def main():
    all_df = load_all_records()
    mutant_df = aggregate_to_mutant_level(all_df)

    print(f"[INFO] Aggregated to {len(mutant_df)} mutants")

    theta_values = np.arange(0.0, 1.0 + 1e-6, THETA_STEP)
    project_results = []

    for project, proj_df in mutant_df.groupby("project"):
        print(f"[INFO] Processing project {project}")

        rows = []
        for theta in theta_values:
            metrics = evaluate_theta(proj_df, theta)
            metrics["project"] = project
            rows.append(metrics)

        results_df = pd.DataFrame(rows)
        best_row = select_best_theta(results_df)
        best_theta = best_row["theta"]

        # 打印时考虑 AUC 可能为空
        auc_val = best_row['auc']
        auc_str = f"{auc_val:.4f}" if auc_val is not None else "N/A"
        print(
            f"[INFO] {project}: theta*={best_theta:.2f}, "
            f"Precision={best_row['precision']:.4f}, "
            f"AUC={auc_str}"
        )

        project_results.append(best_row)

        # 保存 CSV
        out_dir = os.path.join(OUTPUT_ROOT, f"{project}")
        os.makedirs(out_dir, exist_ok=True)

        results_df.to_csv(
            os.path.join(out_dir, "theta_sweep_metrics.csv"),
            index=False
        )
        proj_df.to_csv(
            os.path.join(out_dir, "mutant_aggregated.csv"),
            index=False
        )
        with open(os.path.join(out_dir, "theta_star.txt"), "w") as f:
            f.write(str(best_theta))

    # 汇总所有项目
    summary_df = pd.DataFrame(project_results)
    summary_df.to_csv(
        os.path.join(OUTPUT_ROOT, f"theta_star_summary_{MUTATION_TYPE}.csv"),
        index=False
    )

    print("[OK] Project-wise theta evaluation finished.")

        # =====================================================
    # =============== Global θ (Whole D4J) ================
    # =====================================================
    if RUN_GLOBAL_THETA:
        print("[INFO] Processing GLOBAL (D4J-level) theta")

        global_rows = []
        for theta in theta_values:
            metrics = evaluate_theta(mutant_df, theta)
            metrics["project"] = "ALL"
            global_rows.append(metrics)

        global_results_df = pd.DataFrame(global_rows)

        best_global_row = select_best_theta(global_results_df)
        best_global_theta = best_global_row["theta"]

        auc_val = best_global_row["auc"]
        auc_str = f"{auc_val:.4f}" if auc_val is not None else "N/A"

        print(
            f"[INFO] GLOBAL: theta*={best_global_theta:.2f}, "
            f"Precision={best_global_row['precision']:.4f}, "
            f"AUC={auc_str}"
        )

        # 保存 global 结果
        global_dir = os.path.join(OUTPUT_ROOT, "GLOBAL")
        os.makedirs(global_dir, exist_ok=True)

        global_results_df.to_csv(
            os.path.join(global_dir, "theta_sweep_metrics_global.csv"),
            index=False
        )

        with open(os.path.join(global_dir, "theta_star_global.txt"), "w") as f:
            f.write(str(best_global_theta))


# =========================================================

if __name__ == "__main__":
    main()
