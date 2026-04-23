import csv
from fileinput import filename
import os
import json
import Utils
from pathlib import Path
import pandas as pd
import logging
from SusFormulas import F_Sus
from Utils import get_projects, get_versions

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
################################## Path Load #################################
software_testing_root_env = os.getenv("SOFTWARE_TESTING_ROOT")
if software_testing_root_env is None:
    raise EnvironmentError("The SOFTWARE_TESTING_ROOT environment variable is not set.")

SOFTWARE_TESTING_ROOT = Path(software_testing_root_env)  # 系统根路径
RANK = SOFTWARE_TESTING_ROOT / "FaultLocalization/MBFL/Rank"  # 本代码的输入部分，梯度rank，Rank相关路径，便于之后代码拼接
METRIC = SOFTWARE_TESTING_ROOT / "FaultLocalization/MBFL/Metric"

CheckOrNot = False  # CheckOrNot表示是否进行文件已经存在的检查并跳过的操作
# 配置日志
log_file_path = METRIC / "error_log.txt"  # 假设日志文件位于这个路径
logging.basicConfig(level=logging.ERROR, filename=log_file_path, filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')

################################## File Processor #################################
# 返回为False表示不会进行检查或者文件不存在，仍然需要写入
def check_file_exists(file_path):
    # checkOrNot表示是否
    if CheckOrNot:
        file = Path(file_path)
        return file.exists()
    else:
        return False


# 输入一个项目返回该该项目的所有错误行的json格式的数据，{"1":["xxxx.java-233", "xxxx.java-122"]}
def read_rank_file(file_path):
    return pd.read_csv(file_path)


def write_to_csv(data_frame, file_path):
    print(file_path)
    directory = file_path.parent
    # 如果目录不存在，则创建它
    if not directory.exists():
        directory.mkdir(parents=True)
    # 现在可以安全地写入文件了
    data_frame.to_csv(file_path, index=False)


def calculate_topN(base_path, output_path, project, versions, formula):
    N = [1, 3, 5, 10]
    data_frame = pd.DataFrame(columns=[f'top{n}' for n in N])
    data_frame.loc[0] = [0 for n in N]
    data_frame = data_frame.astype(int)
    for i in versions:
        rank_file_path = base_path / f"{i}" / f"{formula}.csv"
        path = output_path / f"{i}" / f"{formula}.csv"
        if not check_file_exists(path):
            if rank_file_path.exists():
                rank_df = read_rank_file(rank_file_path)
                faulty_rows = rank_df[rank_df['faulty_status'] == True]
                frame = pd.DataFrame({f"top{n}": [faulty_rows['rank'].apply(lambda x: x <= n).sum()] for n in N})
                # 使用loc[0]来更新累积值
                ''''
                    for col in data_frame.columns: 这个循环遍历data_frame中的每一列。data_frame.columns返回的是一个包含data_frame所有列名的索引对象。
                    data_frame.loc[0, col] += frame.loc[0, col] 这行代码执行累加操作。
                    data_frame.loc[0, col]引用的是data_frame中第0行、名为col的列的单元格。frame.loc[0, col]引用的是frame中第0行、名为col的列的单元格。
                    .loc[]是Pandas的一种索引器，允许通过行标签和列标签选择数据。在这里，0是行标签，col是列标签。
                    +=操作符将frame的值累加到data_frame的相应值上。
                '''
                for col in data_frame.columns:
                    data_frame.loc[0, col] += frame.loc[0, col]
                # print(frame.iloc[0])
                # data_frame += frame.iloc[0]  # 更新累计值
                write_to_csv(frame, path)
        else:
            print(f"跳过{path}··························")
    return data_frame


def calculate_exam(base_path, output_path, project, versions, formula):
    data_frame = pd.DataFrame(columns=['Project', 'Version', 'faulty_entity', 'Rank', 'EXAM'])
    for i in versions:
        rank_file_path = base_path / f"{i}" / f"{formula}.csv"
        path = output_path / f"{i}" / f"{formula}.csv"
        if not check_file_exists(path):        
            if rank_file_path.exists():     
                rank_df = read_rank_file(rank_file_path)
                faulty_rows = rank_df[rank_df['faulty_status'] == True]
                frame = pd.DataFrame(
                    {
                        'Project': project,
                        'Version': i,
                        'faulty_entity': faulty_rows['code_entity_linenum'],
                        'Rank': faulty_rows['rank'],
                        'EXAM': faulty_rows['rank'] / rank_df.shape[0]
                    }
                )
                data_frame = pd.concat([data_frame, frame], ignore_index=True)
                write_to_csv(frame, path)
        else:
            print(f"跳过{path}··························")
    return data_frame


def calculate_mean(base_path, output_path, project, versions, formula):
    frame_faulty = pd.DataFrame(columns=['MFR', 'MAR', 'MAP'])
    for i in versions:
        rank_file_path = base_path / f"{i}" / f"{formula}.csv"
        path = output_path / f"{i}" / f"{formula}.csv"
        if not check_file_exists(path):
            if rank_file_path.exists():
                rank_df = read_rank_file(rank_file_path)  # Assuming this function is defined somewhere
                faulty_rows = rank_df[rank_df['faulty_status'] == True]
                # Compute statistics for the current version
                if not faulty_rows.empty:
                    MFR = faulty_rows['rank'].min()  # Assuming MFR is the minimum rank
                    MAR = faulty_rows['rank'].mean()
                    MAP = (1 / faulty_rows['rank']).mean()
                    
                    # Create a DataFrame with the statistics for the current version
                    data_frame = pd.DataFrame(
                        {
                            'MFR': [MFR], 
                            'MAR': [MAR], 
                            'MAP': [MAP]
                        }
                    )
                    write_to_csv(data_frame, path)  # Assuming this function is defined somewhere
                    
                    frame_faulty = pd.concat([frame_faulty, data_frame], ignore_index=True)
        else:
            print(f"跳过{path}··························")
    
    # Calculate the average row for frame_faulty
    if not frame_faulty.empty:
        average_row = frame_faulty.mean()
        # Create a new DataFrame with the average row and the original columns
        average_df = pd.DataFrame([average_row], columns=frame_faulty.columns)
        return average_df
    else:
        # Return an empty DataFrame if there are no versions to process
        return pd.DataFrame(columns=frame_faulty.columns)

def get_metric(*args):
    # 逻辑处理开始，首先根据参数构造路径
    project, versions, granularity, dataset, dataset_version, mutanttype, tool, approach, killtype, aggregation, tieBreak, formula, metric = args
    base_path = RANK / granularity / dataset / dataset_version / mutanttype / tool / approach / killtype / aggregation / tieBreak / project
    output_path = METRIC / granularity / dataset / dataset_version / mutanttype / tool / approach / killtype / aggregation / tieBreak / metric / project
    file_path = output_path / "Summary" / f"{formula}.csv"
    # 根据不同的metric调用不同的处理函数
    if metric == "TopN":
        data_frame = calculate_topN(base_path, output_path, project, versions, formula)
    elif metric == "EXAM":
        data_frame = calculate_exam(base_path, output_path, project, versions, formula)
    elif metric == "MEAN":
        data_frame = calculate_mean(base_path, output_path, project, versions, formula)
    else:
        raise ValueError("Unsupported metric")
    # 最后，将累计的结果写入总的输出文件
    if not data_frame.empty:
        write_to_csv(data_frame, file_path)


def init(project, versions):
    # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
    # MutationType = ["NeuralMutation", "TraditionalMutation", "MergeMutation", "MergeSus"]
    MutationType = [ "NeuralMutation"]
    Tool = {
        # "NeuralMutation": ["mBERT", "mBERT_fourier_2","mBERT_flim","mBERT_flim_soft","mBERT_flim_oracle","mBERT_flim_hard8","mBERT_flim_topk70_llm"],
        # "NeuralMutation": ["mBERT_flim_topk30_llm","mBERT_flim_topk50_llm","mBERT_flim_topk70_llm","mBERT_flim_topk30_random","mBERT_flim_topk50_random","mBERT_flim_topk70_random"],
        # "NeuralMutation": ["mBERT_flim_soft"],
        "NeuralMutation": ["mBERT_flim_topk30_llm","mBERT_flim_topk50_llm","mBERT_flim_topk70_llm"]
        # "TraditionalMutation": ["major", "major_fourier_2","major_flim","major_flim_soft","major_flim_oracle","major_flim_hard8","major_flim_topk70_llm"],
        # "TraditionalMutation": ["major_flim_topk30_llm","major_flim_topk50_llm","major_flim_topk70_llm","major_flim_topk30_random","major_flim_topk50_random","major_flim_topk70_random"],
        # "TraditionalMutation": ["major_flim_topk30_llm","major_flim_topk50_llm","major_flim_topk70_llm"],
        # "TraditionalMutation": ["major_flim_soft"],
        # "MergeMutation": [
        #     "major_SmBERT_soft", "major_SmBERT_soft_fourier_2",
        #     "mBERT_Smajor_soft", "mBERT_Smajor_soft_fourier_2",
        #     "U_mBERT_major_soft", "U_mBERT_major_soft_fourier_2",
        #     "major_SmBERT_hard", "major_SmBERT_hard_fourier_2",
        #     "mBERT_Smajor_hard", "mBERT_Smajor_hard_fourier_2",
        #     "U_mBERT_major_hard", "U_mBERT_major_hard_fourier_2"
        # ],

        # "MergeSus": ["BordaCountAvg", "SusDRankAvg", "SusAvg"]
        # "MergeSus": ["BordaCountAvg", "SusAvg"]
    }
    # MutantSources = ["mBERT","major"]
    Dataset = ["Defects4J"]
    DatasetVersion = {
        "Defects4J": ["D4JCleanCD4J"],  # "D4JCleanCD4J", "Defects4J_v2.0.0"
    }
    Granularity = ["Statement"]  # "Function","Statement","Mutant"
    # KillType = ["kill_type13"]
    KillType = ["kill_type1", "kill_type3"]
    Approach = ["FACombination"]
    Aggregation = ["max", "avg", "max-avg", "max+avg"]
    TieBreak = ["Best", "Avg"]
    Metric = ["TopN", "EXAM", "MEAN"]
    Formula = list(F_Sus.keys())
    for granularity in Granularity:
        for dataset in Dataset:
            for dataset_version in DatasetVersion[dataset]:
                for mutationtype in MutationType:
                    tools = Tool[mutationtype]
                    for tool in tools:
                        for approach in Approach:
                            for killtype in KillType:
                                for aggregation in Aggregation:
                                    for tiebreak in TieBreak:
                                        for formula in Formula:
                                            for metric in Metric:
                                                try:
                                                    get_metric(project, versions, granularity, dataset, dataset_version, mutationtype, tool,
                                                                approach, killtype, aggregation, tiebreak, formula,
                                                                metric)
                                                except Exception as e:
                                                    error_message = f"Error occurred: {project}-{dataset}-{dataset_version}-{mutationtype}-{tool}-{killtype}-{approach}-{aggregation}-{tiebreak}-{formula}-{metric}: {e}"
                                                    logging.error(error_message)
                                                    print(error_message)


if __name__ == '__main__':
    projects = get_projects()
    # projects = ["Collections", "Compress", "JacksonDatabind", "Jsoup", "JxPath"]
    # projects = ["Time"]
    print(f"获取到的项目总数: {len(projects)}")

    for idx, project in enumerate(projects, start=1):
        print("~"*50)
        print(f"正在处理第 {idx} 个项目: {project}")

        versions = get_versions(project)
        print(f"该项目的版本数量: {len(versions)}")
        init(project, versions)