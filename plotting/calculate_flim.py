#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FLIM统计脚本（增强版）

功能：
1. 计算每个 version 的 mutant 分布
2. 计算 FLIM Ratio（误导占比）
3. 🔥新增：FLIM Density（误导规模）
4. 输出：
   - version级 CSV
   - project级 Summary
   - tool级 Overall Summary
"""

import os
import pandas as pd
import glob
from pathlib import Path

# ====================== 输出路径 ======================
CSV_ROOT_PATH = "/home/rs/WorkEx/Projects/SoftwareTesting/0ExperimentPlayGround/fxj/flim_radio"


def create_directory_if_not_exists(dir_path):
    """创建目录（如果不存在）"""
    Path(dir_path).mkdir(parents=True, exist_ok=True)
    return dir_path


def calculate_mutant_statistics(projects=None, mutation_tools_config=None, kill_types=None):
    """
    主函数：计算所有统计指标
    """

    # ====================== 默认配置 ======================
    if projects is None:
        projects = ["Time", "Mockito", "Math", "Lang", "JxPath", "Jsoup", "JacksonXml", "JacksonDatabind",
                    "JacksonCore", "Gson", "Csv", "Compress", "Collections", "Codec", "Closure", "Cli", "Chart"]

    if mutation_tools_config is None:
        mutation_tools_config = {
            "NeuralMutation": ["mBERT"],
            "TraditionalMutation": ["major"]
        }

    if kill_types is None:
        kill_types = ["kill_type3"]

    base_path = "/home/rs/WorkEx2/Projects/SoftwareTesting/FaultLocalization/MBFL/Sus/Mutant/Defects4J/D4JCleanCD4J"

    print("\n开始计算变异体统计信息...")

    # ====================== 数据结构 ======================
    tool_project_data = {}
    for mutation_type in mutation_tools_config:
        for tool in mutation_tools_config[mutation_type]:
            tool_project_data.setdefault(tool, {})
            for project in projects:
                tool_project_data[tool][project] = []

    # ====================== 遍历数据 ======================
    for project in projects:
        print(f"\n处理项目: {project}")

        for kill_type in kill_types:
            for mutation_type in mutation_tools_config:
                for tool in mutation_tools_config[mutation_type]:

                    file_pattern = os.path.join(
                        base_path, mutation_type, tool, kill_type, project, f"{project}_*.xlsx"
                    )
                    excel_files = glob.glob(file_pattern)

                    for excel_file in excel_files:
                        filename = os.path.basename(excel_file)
                        vision = filename.replace(f"{project}_", "").replace(".xlsx", "")

                        try:
                            df = pd.read_excel(excel_file)

                            # 必要字段检查
                            if not {'faulty_status', 'akf'}.issubset(df.columns):
                                continue

                            # ====================== 基础统计 ======================
                            total_mutants = len(df)

                            faulty_df = df[df['faulty_status'] == True]
                            correct_df = df[df['faulty_status'] == False]

                            faulty_total = len(faulty_df)
                            correct_total = len(correct_df)

                            faulty_akf_ge1 = len(faulty_df[faulty_df['akf'] >= 1])
                            correct_akf_ge1 = len(correct_df[correct_df['akf'] >= 1])

                            faulty_akf_eq0 = len(faulty_df[faulty_df['akf'] == 0])
                            correct_akf_eq0 = len(correct_df[correct_df['akf'] == 0])

                            # ====================== 比例 ======================
                            faulty_rate = round(faulty_total / total_mutants if total_mutants else 0, 4)
                            correct_rate = round(correct_total / total_mutants if total_mutants else 0, 4)

                            # ====================== FLIM计算 ======================

                            # FLIM Ratio（误导占比）
                            flim_denominator = faulty_akf_ge1 + correct_akf_ge1
                            flim_rate = round(
                                correct_akf_ge1 / flim_denominator
                                if flim_denominator > 0 else 1.0,
                                4
                            )

                            # 🔥 FLIM Density（误导规模）
                            flim_density = round(
                                correct_akf_ge1 / total_mutants
                                if total_mutants > 0 else 0,
                                4
                            )

                            # ====================== 存储 ======================
                            tool_project_data[tool][project].append({
                                'vision': vision,
                                'project': project,
                                'tool': tool,

                                'total_mutants': total_mutants,

                                'faulty_total': faulty_total,
                                'faulty_akf_ge1': faulty_akf_ge1,
                                'faulty_akf_eq0': faulty_akf_eq0,

                                'correct_total': correct_total,
                                'correct_akf_ge1': correct_akf_ge1,
                                'correct_akf_eq0': correct_akf_eq0,

                                'faulty_rate': faulty_rate,
                                'correct_rate': correct_rate,

                                'flim_denominator': flim_denominator,
                                'flim_rate': flim_rate,

                                # 🔥 NEW
                                'flim_density': flim_density
                            })

                        except Exception as e:
                            print(f"读取失败: {excel_file} -> {e}")

    # ====================== 输出 CSV ======================
    for tool in tool_project_data:
        for project in tool_project_data[tool]:

            data = tool_project_data[tool][project]
            if not data:
                continue

            df_csv = pd.DataFrame(data)
            df_csv['vision'] = pd.to_numeric(df_csv['vision'], errors='ignore')
            df_csv = df_csv.sort_values('vision')

            project_dir = create_directory_if_not_exists(
                os.path.join(CSV_ROOT_PATH, tool, project)
            )

            csv_path = os.path.join(project_dir, f"{project.lower()}.csv")
            df_csv.to_csv(csv_path, index=False, encoding='utf-8-sig')

            # ====================== Project Summary ======================
            summary = {
                'project': project,
                'tool': tool,

                'version_count': len(df_csv),
                'total_mutants': df_csv['total_mutants'].sum(),

                'faulty_total_sum': df_csv['faulty_total'].sum(),
                'correct_total_sum': df_csv['correct_total'].sum(),

                'flim_denominator_sum': df_csv['flim_denominator'].sum(),

                # Ratio（平均）
                'flim_rate_avg': round(df_csv['flim_rate'].mean(), 4),

                # 🔥 Density（平均）
                'flim_density_avg': round(df_csv['flim_density'].mean(), 4)
            }

            pd.DataFrame([summary]).to_csv(
                os.path.join(project_dir, "Summary.csv"),
                index=False,
                encoding='utf-8-sig'
            )

    # ====================== Overall Summary ======================
    for tool in tool_project_data:

        rows = []
        for project in tool_project_data[tool]:
            path = os.path.join(CSV_ROOT_PATH, tool, project, "Summary.csv")
            if os.path.exists(path):
                rows.append(pd.read_csv(path).iloc[0])

        if not rows:
            continue

        df_all = pd.DataFrame(rows)

        overall = {
            'project': 'ALL_D4J',
            'tool': tool,

            'version_count': df_all['version_count'].sum(),
            'total_mutants': df_all['total_mutants'].sum(),

            # 🔥 两个指标
            'flim_rate_avg': round(df_all['flim_rate_avg'].mean(), 4),
            'flim_density_avg': round(df_all['flim_density_avg'].mean(), 4)
        }

        df_all = pd.concat([df_all, pd.DataFrame([overall])], ignore_index=True)

        df_all.to_csv(
            os.path.join(CSV_ROOT_PATH, tool, "Overall_Summary.csv"),
            index=False,
            encoding='utf-8-sig'
        )

    print("\n✅ 所有数据生成完成！")


# ====================== 入口 ======================
if __name__ == "__main__":
    calculate_mutant_statistics()