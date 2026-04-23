import ast
import csv
import glob
import json
import os
import subprocess
import pandas as pd
import Utils
from tkinter import NO
from pathlib import Path
import logging
from SusFormulas import F_Sus
from Utils import get_projects, get_versions

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
################################## Path Load #################################
software_testing_root_env = os.getenv("SOFTWARE_TESTING_ROOT")
if software_testing_root_env is None:
    raise EnvironmentError("The SOFTWARE_TESTING_ROOT environment variable is not set.")
SOFTWARE_TESTING_ROOT = Path(software_testing_root_env)  # 系统根路径
SUS = SOFTWARE_TESTING_ROOT / "FaultLocalization/MBFL/Sus"
Mutant_Test_Result = SOFTWARE_TESTING_ROOT / "MutationAnalysis/MutantTestResult"  # 本代码的输入文件,存放变异测试产生的一些failingTest   之后再拼接mbert和major的result4FaultFile
Sus_MBFL_FL = SOFTWARE_TESTING_ROOT / "FaultLocalization/MBFL/Sus"  # 本代码的输出文件，Sus相关路径，便于以后代码拼接
CheckOrNot = False  # CheckOrNot表示是否进行文件已经存在的检查并跳过的操作
# 配置日志
log_file_path = SUS / "Statement/Defects4J/error_log.txt"  # 假设日志文件位于这个路径
logging.basicConfig(level=logging.ERROR, filename=log_file_path, filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')
################################## File Processor #################################
# 返回为False表示不会进行检查或者文件不存在，仍然需要写入
def check_file_exists(file_path):
    # checkOr表示是否
    if CheckOrNot:
        file = Path(file_path)
        return file.exists()
    else:
        return False


def write_dataframe_to_csv(file_path, dataframe):
    # 使用Path对象处理路径
    file_path = Path(file_path)

    # 检查父目录是否存在，如果不存在，则创建
    if not file_path.parent.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)

    # 将DataFrame写入到CSV文件
    dataframe.to_csv(file_path, index=False)
    print(f"写入csv文件 {file_path}")


def processExcel_FACombination(excel_file_path, output_csv_path,
                               aggregation):  # 处理FaultLocalization/MBFL/Sus/Mutant/Defects4J/major/kill_type1/Chart/Chart_1.xlsx文件的逻辑公式
    excel_file = pd.ExcelFile(excel_file_path)
    sheet_names = excel_file.sheet_names
    output_csv_path.mkdir(parents=True, exist_ok=True)  # 确保目录存在
    # 遍历每个表
    # 遍历每个工作表并处理
    for sheet in sheet_names:

        # ================= 新增：保护性读取 sheet =================
        try:
            # 加载工作表到DataFrame
            df = pd.read_excel(excel_file_path, sheet_name=sheet)
        except Exception as e:
            # 如果某个 sheet 无法正常读取（如文件损坏、XML 异常等），直接跳过
            print(f"[WARN] Skip unreadable sheet: {excel_file_path} | sheet={sheet}")
            print(f"       Reason: {e}")
            continue
        # ==========================================================
        # 加载工作表到DataFrame
        df = pd.read_excel(excel_file_path, sheet_name=sheet)
        # 计算每个linenum分组内Sus列的平均值
        # 按version,code_entity'和'linenum'分组，然后将'Sus'聚合成一个列表
        grouped = df.groupby(['version', 'code_entity', 'linenum']).agg({'Sus': lambda x: list(x)}).reset_index()
        # 对每组的'Sus'列表应用'process_sus_list'函数
        grouped['sus_line'] = grouped['Sus'].apply(lambda x: Utils.process_sus_list(x, aggregation))
        # 将grouped的code_entity列和linenum拼接，形成一个新的一列
        grouped['code_entity_linenum'] = grouped['code_entity'] + "-" + grouped['linenum'].astype(str)
        # 将code_entity_linenum作为第一列， sus_line作为第二列这两列提取，保存成csv文件
        selected_columns = grouped[['code_entity_linenum', 'sus_line']]
        # # 按照'sus_line'的值降序排列
        selected_columns = (
            grouped[['code_entity_linenum', 'sus_line']]
            .copy()
            .sort_values(by='sus_line', ascending=False)
        )

        output_csv_file = output_csv_path / f"{sheet}.csv"
        # 将结果输出到CSV文件，每个工作表一个文件
        write_dataframe_to_csv(output_csv_file,selected_columns)


# 下面是本代码的核心处理逻辑，将变异体的怀疑度转换为行的怀疑度：
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
def getLineSus(project, version, dataset, dataset_version, mutanttype, tool, killtype, approach, aggregation):
    # 输入，mutantSus对应的excel文件
    excel_file_path = SUS / "Mutant" / dataset / dataset_version / mutanttype / tool / killtype / project / f"{project}_{version}.xlsx"
    # 输出文件夹，文件行怀疑度对应的csv文件
    output_csv_path = SUS / "Statement" / dataset / dataset_version / mutanttype / tool / approach / killtype / aggregation / project / version
    if not check_file_exists(output_csv_path):  # 该文件不存在，或者不进行检查
        print(f"输入文件夹是{excel_file_path}，输出文件夹是{output_csv_path}")
        # 按照sheet转换成各个csv格式并输出
        processExcel_FACombination(excel_file_path, output_csv_path, aggregation)
    else:
        print(f"we have already processed {excel_file_path}")


def init(project, version):
    # MutationType = ["NeuralMutation", "TraditionalMutation", "MergeMutation"]
    # MutationType = ["NeuralMutation", "TraditionalMutation"]
    # MutationType = ["TraditionalMutation"]
    MutationType = ["NeuralMutation"]
    Tool = {
        # "NeuralMutation": ["mBERT", "mBERT_fourier_2","mBERT_flim","mBERT_flim_soft","mBERT_flim_oracle","mBERT_flim_hard8","mBERT_flim_topk70_llm"],
        # "NeuralMutation": ["mBERT_flim_topk30_oracle_akf","mBERT_flim_topk50_oracle_akf","mBERT_flim_topk70_oracle_akf","mBERT_flim_topk30_oracle_random","mBERT_flim_topk50_oracle_random","mBERT_flim_topk70_oracle_random"],
        # "NeuralMutation": ["mBERT_flim_topk30_llm","mBERT_flim_topk50_llm","mBERT_flim_topk70_llm","mBERT_flim_topk30_random","mBERT_flim_topk50_random","mBERT_flim_topk70_random"],
        # "NeuralMutation": ["mBERT_flim_soft",],
        "NeuralMutation": ["mBERT_flim_topk30_llm","mBERT_flim_topk50_llm","mBERT_flim_topk70_llm"],
        # "TraditionalMutation": ["major", "major_fourier_2","major_flim","major_flim_soft","major_flim_oracle","major_flim_hard8","major_flim_topk70_llm"],
        # "TraditionalMutation": ["major_flim_topk30_oracle_akf","major_flim_topk50_oracle_akf","major_flim_topk70_oracle_akf","major_flim_topk30_oracle_random","major_flim_topk50_oracle_random","major_flim_topk70_oracle_random"],
        # "TraditionalMutation": ["major_flim_topk30_llm","major_flim_topk50_llm","major_flim_topk70_llm","major_flim_topk30_random","major_flim_topk50_random","major_flim_topk70_random"],
        # "TraditionalMutation": ["major_flim_soft"],
        # "MergeMutation": [
        #     "major_SmBERT_soft", "major_SmBERT_soft_fourier_2",
        #     "mBERT_Smajor_soft", "mBERT_Smajor_soft_fourier_2",
        #     "U_mBERT_major_soft", "U_mBERT_major_soft_fourier_2",
        #     "major_SmBERT_hard", "major_SmBERT_hard_fourier_2",
        #     "mBERT_Smajor_hard", "mBERT_Smajor_hard_fourier_2",
        #     "U_mBERT_major_hard", "U_mBERT_major_hard_fourier_2"
        # ]
        # "MergeMutation": [
        #     "major_SmBERT_soft_fourier_2",
        #     "mBERT_Smajor_soft_fourier_2",
        #     "U_mBERT_major_soft_fourier_2",
        #     "major_SmBERT_hard_fourier_2",
        #     "mBERT_Smajor_hard_fourier_2",
        #     "U_mBERT_major_hard_fourier_2"
        # ]
    }
    # MutantSources = ["mBERT","major"]
    Dataset = ["Defects4J"]
    DatasetVersion = {
        "Defects4J": ["D4JCleanCD4J"],  # "D4JCleanCD4J", "Defects4J_v2.0.0"
    }
    Granularity = ["Mutant"]  # "Function","Statement","Mutant"
    # KillType = ["kill_type1", "kill_type3", "kill_type13", "kill_type1+3"]
    KillType = ["kill_type3"]
    Approach = ["FACombination"]
    # Aggregation = ["max", "avg", "max-avg", "max+avg"]
    Aggregation = ["max", "avg", "max-avg", "max+avg"]

    Formula = list(F_Sus.keys())
    for mutationtype in MutationType:
        tools = Tool[mutationtype]
        for tool in tools:
            for dataset in Dataset:
                for dataset_version in DatasetVersion[dataset]:
                    for killtype in KillType:
                        for approach in Approach:
                            for aggregation in Aggregation:
                                # getLineSus(project, f"{version}", dataset, dataset_version,  mutationtype, tool, killtype, approach, aggregation)
                                try:
                                    getLineSus(project, f"{version}", dataset, dataset_version, mutationtype, tool, killtype, approach, aggregation)
                                except Exception as e:
                                    error_message = f"Error occurred: {project}-{version}-{dataset}-{dataset_version}-{mutationtype}-{tool}-{killtype}-{approach}-{aggregation}: {e}"
                                    logging.error(error_message)
                                    print(error_message)


def run_Time_AllVersions():
    """运行Time项目所有版本的语句怀疑度计算"""
    print("开始运行Time项目所有版本的语句怀疑度计算")
    project = "Time"
    versions = get_versions(project)
    print(f"Time项目的版本数量: {len(versions)}")

    for idx, version in enumerate(versions, start=1):
        print("-" * 50)
        print(f"正在处理第 {idx}/{len(versions)} 个版本: {version}")
        try:
            init(project, version)
            print(f"版本 {version} 处理完成")
        except Exception as e:
            error_message = f"处理版本 {version} 时发生错误: {e}"
            logging.error(error_message)
            print(error_message)

    print("Time项目所有版本的语句怀疑度计算完成")

def run_AllProjects_AllVersions():
    """运行所有 Defects4J 项目的所有版本"""
    print("开始运行所有 Defects4J 项目的语句怀疑度计算")

    projects = get_projects()
    print(f"项目总数: {len(projects)}")

    for p_idx, project in enumerate(projects, start=1):
        print("=" * 80)
        print(f"正在处理第 {p_idx}/{len(projects)} 个项目: {project}")

        try:
            versions = get_versions(project)
            print(f"{project} 项目的版本数量: {len(versions)}")
        except Exception as e:
            error_message = f"获取项目 {project} 的版本失败: {e}"
            logging.error(error_message)
            print(error_message)
            continue

        for v_idx, version in enumerate(versions, start=1):
            print("-" * 50)
            print(f"[{project}] 正在处理版本 {v_idx}/{len(versions)}: {version}")

            try:
                init(project, version)
                print(f"[{project}] 版本 {version} 处理完成")
            except Exception as e:
                error_message = (
                    f"处理失败: {project}-{version}: {e}"
                )
                logging.error(error_message)
                print(error_message)

    print("所有项目的语句怀疑度计算完成")



if __name__ == '__main__':
    run_AllProjects_AllVersions()
    # run_Time_AllVersions()
