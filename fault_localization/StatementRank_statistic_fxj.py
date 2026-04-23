import csv
from fileinput import filename
import os
import json
import Utils
from pathlib import Path
import numpy as np
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
Mutant_Faulty_Path = SOFTWARE_TESTING_ROOT / "DataSet/Defects4J/D4JClean/faultyLinePlus"  # 语句级错误行的路径
Mutant_Faulty_Path_D4J = SOFTWARE_TESTING_ROOT / "DataSet/Defects4J/D4J/Faultline_D4J.json"  # 语句级错误行的路径
SUS = SOFTWARE_TESTING_ROOT / "FaultLocalization/MBFL/Sus"  # 本代码的输入文件，语句怀疑度，Sus相关路径，便于以后代码拼接
RANK = SOFTWARE_TESTING_ROOT / "FaultLocalization/MBFL/Rank"  # 本代码的输出部分，梯度rank，Rank相关路径，便于之后代码拼接
CheckOrNot = False  # CheckOrNot表示是否进行文件已经存在的检查并跳过的操作
# 配置日志
log_file_path = RANK/"error_log.txt"  # 假设日志文件位于这个路径
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


# 读取txt
def read_txt_file(file_path):
    lines = []
    with open(file_path, 'r') as f:
        for line in f:
            lines.append(line.strip())
    return lines


# 将错误行的信息处理成和sus列表中的格式相同
def changeTxtEqualCsv(mutant_dic):
    faultyList = []
    for key, value in mutant_dic.items():
        #   faultyLine = key[len(sourceFilePath):].split(".")[0].replace("/", "-")
        faultyLine = key[1:].split(".")[0].replace("/", "-")
        for lineNum in value:
            # 之后要重写 这是转储命名有问题
            # tmp = faultyLine + "-" + str(lineNum)
            # tmp = tmp.split('-')
            # del tmp[-2]
            # tmp = '-'.join(tmp)
            # faultyList.append(tmp)
            # 到这里结束
            faultyList.append(faultyLine + "-" + str(lineNum))
    return faultyList


# 获取rank及csv数据,下面有问题
def get_rank_statement(csv_path):
    # 存储value值与排名的映射关系
    value_rank_dict = {}
    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        # next(reader) # 跳过header
        sus = {}
        rank = 1
        num = 1
        for row in reader:
            sus[row[0]] = row[1]
            value = str(row[1])
            if value not in value_rank_dict:
                # rank = num
                value_rank_dict[value] = rank
                rank += 1
            # num += 1
    return sus, value_rank_dict


# 生成csv
def load_csv(path, content, formula, rank, faultylist):
    try:
        ans = {}  # type: dict[str, dict[str, int]]
        for key, value in content.items():  # key: "src-main-java-org-apache-commons-lang3-math-NumberUtils-1414", value: {"rank": 1, "faulty": false}
            ans[key] = {
                "rank": rank[value],
                "faulty": True if key in faultylist else False,
                "sus": value
            }
        with open(f"{path}/{formula}.json", 'w') as f:
            json.dump(ans, f)
        return True
    except:
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

def convert_str_to_dict(s):
    start_index = 0
    result = {}
    while True:
        key_start_index = s.find("'", start_index) + 1
        if key_start_index == 0:
            break
        key_end_index = s.find("'", key_start_index)
        key = s[key_start_index:key_end_index]
        value_start_index = s.find("[", key_end_index) + 1
        value_end_index = s.find("]", value_start_index)
        value_str = s[value_start_index:value_end_index]
        if value_str:
            value = list(map(int, value_str.split(",")))
            result[key] = value
        start_index = value_end_index
    return result


# 输入一个项目返回该该项目的所有错误行的json格式的数据，{"1":["xxxx.java-233", "xxxx.java-122"]}
def getFaultyLineJson(pid):
    mutant_path = Mutant_Faulty_Path / f"{pid}FaultLine.txt"
    faultyInfo = read_txt_file(mutant_path)  # 错误行信息!
    faultyList = {}
    for _item in faultyInfo:  # 遍历每一行
        versions = _item.split(" ")[1]
        # 获取错误行信息
        # mutant = item[(item.index('{') + 1):-1]
        mutant = _item[(_item.index('{')):]
        mutant_dic = convert_str_to_dict(mutant)
        faultyList[versions] = changeTxtEqualCsv(mutant_dic)
    return faultyList


def getCodeEntityLineNum(pid, version, granularity, dataset, dataset_version, mutanttype, tool, approach, killtype, aggregation, tieBreak, formula):
    # 读取statments_sus.csv, 并获取code_entity_linenum的dataframe
    if mutanttype == "MergeSus":
        statement_sus_path = SUS / "Statement" / dataset/ dataset_version / mutanttype / tool / approach / killtype / aggregation / tieBreak / pid / version / f"{formula}.csv"
    else:
        statement_sus_path = SUS / "Statement" / dataset/ dataset_version / mutanttype / tool / approach / killtype / aggregation / pid / version / f"{formula}.csv"
    # 调用pandas将csv转换为dataframe方便处理
    df = pd.read_csv(statement_sus_path)
    return df['code_entity_linenum'].to_frame()

#
def getRank(pid, version, granularity, dataset, dataset_version, mutanttype, tool, approach, killtype, aggregation, tieBreak, formula, code_entity_linenum_df=None, fillna_strategy='fill_lower_than_min'):
    """
    fillna_strategy: ['neglect', 'fill_min', 'fill_lower_than_min']
    """
    
    # 读取错误行对于的json文件
    faultyFileJson = getFaultyLineJson(pid)
    if pid in ["Collections","JacksonDatabind", "JxPath"]:
        with open(Mutant_Faulty_Path_D4J, 'r') as f:
            Json_file = json.load(f)
        faultyFileJson = Json_file[pid] # 这里用新的faultyline
    # 读取statments_sus.csv,这里不用granularity
    if mutanttype == "MergeSus":
        statement_sus_path = SUS / "Statement" / dataset / dataset_version / mutanttype / tool / approach / killtype / aggregation / tieBreak / pid / version / f"{formula}.csv"
    else:
        statement_sus_path = SUS / "Statement" / dataset / dataset_version / mutanttype / tool / approach / killtype / aggregation / pid / version / f"{formula}.csv"
    # 输出文件 FaultLocalization/MBFL/Rank/Statement/Defects4J/NeuralMutation/mBERT/Metallaxis/kill_type1/avg/Avg/Chart/1/Dstar.csv
    output_path = RANK / granularity / dataset / dataset_version / mutanttype / tool / approach / killtype / aggregation / tieBreak / pid / version / f"{formula}.csv"
    if not check_file_exists(output_path):  # 该文件不存在，或者不进行检查
        # 调用pandas将csv转换为dataframe方便处理
        df = pd.read_csv(statement_sus_path)

        # 如果code_entity_linenum_df不为空，则将以code_entity_linenum_df的'code_entity_linenum'为合并列将df合并到df中
        if code_entity_linenum_df is not None:
            df = code_entity_linenum_df.merge(df, on='code_entity_linenum', how='left')

        # 添加标记列，记录哪些位置是原始的空白值
        df['is_missing'] = df['sus_line'].isna()

        # 默认值，用于所有数据为空时的填充
        default_fill_value = 0
        # 如果所有值都为空，填充默认值
        if df['sus_line'].isna().all():
            df['sus_line_processed'] = df['sus_line'].fillna(default_fill_value)
        else:
            # 根据不同策略填充数据
            if fillna_strategy == 'neglect':
                # 不处理空白值
                df['sus_line_processed'] = df['sus_line']
            elif fillna_strategy == 'fill_min':
                # 用最小值替换空白值
                min_value = df['sus_line'].min()
                df['sus_line_processed'] = df['sus_line'].fillna(min_value)
            elif fillna_strategy == 'fill_lower_than_min':
                # 用比最小值小的一个值替换空白值
                min_value = df['sus_line'].min()
                smallest_value = min_value - 1 if pd.notna(min_value) else default_fill_value - 1
                df['sus_line_processed'] = df['sus_line'].fillna(smallest_value)
            else:
                raise ValueError(f"Unknown fillna strategy {fillna_strategy}")
            
        # 利用pandas的生成不同tiebreak的rank值
        if (tieBreak == "Level"):
            # 调用dense方法按照csv的第二列sus_line的值为每一行生成一个值,列名为Rank_Level
            df['rank'] = df['sus_line_processed'].rank(method='dense', ascending=False)
        elif (tieBreak == "Worst"):
            # 调用max方法按照csv的第二列sus_line的值为每一行生成一个值,列名为Rank_Worst
            df['rank'] = df['sus_line_processed'].rank(method='max', ascending=False)
        elif (tieBreak == "Best"):
            # 调用max方法按照csv的第二列sus_line的值为每一行生成一个值,列名为Rank_Best
            df['rank'] = df['sus_line_processed'].rank(method='min', ascending=False)
        elif (tieBreak == "Avg"):
            # 调用average方法按照csv的第二列sus_line的值为每一行生成一个值,列名为Rank_Avg
            df['rank'] = df['sus_line_processed'].rank(method='average', ascending=False)

        # 删除标记列和临时列
        df.drop(columns=['is_missing', 'sus_line_processed'], inplace=True)

        # 比对读取FaultyFile文件，增加一列faulty_status的标志
        list_faultyline = faultyFileJson[version]
        # 增加新的一列，为faulty_status,如果该行的code_entity_linenum在list_faultyline中，增加新的一列，为faulty_status为true，否则为false
        df['faulty_status'] = df['code_entity_linenum'].apply(lambda x: True if x in list_faultyline else False)
        print(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # 输出文件
        df.to_csv(output_path, index=False)
    else:
        print(f"文件已存在: {output_path}")




def init(pid, versions):
    # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
    # MutationType = ["NeuralMutation", "TraditionalMutation", "MergeMutation", "MergeSus"]
    # MutationType = [ "NeuralMutation","TraditionalMutation"]
    MutationType = [ "NeuralMutation"]
    Tool = {
        # "NeuralMutation": ["mBERT", "mBERT_fourier_2","mBERT_flim","mBERT_flim_soft","mBERT_flim_oracle","mBERT_flim_hard8","mBERT_flim_topk70_llm"],
        # "NeuralMutation": ["mBERT_flim_topk30_llm","mBERT_flim_topk50_llm","mBERT_flim_topk70_llm","mBERT_flim_topk30_random","mBERT_flim_topk50_random","mBERT_flim_topk70_random"],
        # "NeuralMutation": ["mBERT_flim_soft"],
        "NeuralMutation": ["mBERT_flim_topk30_llm","mBERT_flim_topk50_llm","mBERT_flim_topk70_llm"]
        # "TraditionalMutation": ["major", "major_fourier_2","major_flim","major_flim_soft","major_flim_oracle","major_flim_hard8","major_flim_topk70_llm"],
        # "TraditionalMutation": ["major_flim_topk30_llm","major_flim_topk50_llm","major_flim_topk70_llm","major_flim_topk30_random","major_flim_topk50_random","major_flim_topk70_oracle_random"],
        # "TraditionalMutation": ["major_flim_soft"],
        # "MergeMutation": [
        #     "major_SmBERT_soft", "major_SmBERT_soft_fourier_2",
        #     "mBERT_Smajor_soft", "mBERT_Smajor_soft_fourier_2",
        #     "U_mBERT_major_soft", "U_mBERT_major_soft_fourier_2",
        #     "major_SmBERT_hard", "major_SmBERT_hard_fourier_2",
        #     "mBERT_Smajor_hard", "mBERT_Smajor_hard_fourier_2",
        #     "U_mBERT_major_hard", "U_mBERT_major_hard_fourier_2"
        # ]
    #     "MergeMutation": [
    #         "major_SmBERT_soft_fourier_2",
    #         "mBERT_Smajor_soft_fourier_2",
    #         "U_mBERT_major_soft_fourier_2",
    #         "major_SmBERT_hard_fourier_2",
    #         "mBERT_Smajor_hard_fourier_2",
    #         "U_mBERT_major_hard_fourier_2"
    #     ]
    }
    # MutantSources = ["mBERT","major"]
    Dataset = ["Defects4J"]
    DatasetVersion = {
        "Defects4J": ["D4JCleanCD4J"],  # "D4JCleanCD4J", "Defects4J_v2.0.0"
    }
    Granularity = ["Statement"]  # "Function","Statement","Mutant"
    # KillType = ["kill_type1", "kill_type3", "kill_type13", "kill_type1+3"]
    KillType = ["kill_type3"]
    Approach = ["FACombination"]
    # Aggregation = ["max", "avg", "max-avg", "max+avg"]
    Aggregation = ["max", "avg", "max-avg", "max+avg"]
    TieBreak = ["Level", "Best", "Avg"]
    Formula = list(F_Sus.keys())
    if "BLMu" not in Formula:
        Formula.append("BLMu")

    for granularity in Granularity:
        for dataset in Dataset:
            for dataset_version in DatasetVersion[dataset]:
                for approach in Approach:
                    for killtype in KillType:
                        for aggregation in Aggregation:
                            for tiebreak in TieBreak:
                                for formula in Formula:
                                    # BLMu specific logic
                                    if killtype == "kill_type1+3":
                                        if formula != "BLMu": continue
                                    else:
                                        if formula == "BLMu": continue
                                    
                                    for version in versions:
                                        # 获取code_entity_linenum_df的并集
                                        code_entity_linenum_dfs = []
                                        for mutationtype in MutationType:
                                            tools = Tool[mutationtype]
                                            for tool in tools:
                                                try:
                                                    code_entity_linenum_df = getCodeEntityLineNum(pid, f"{version}", granularity, dataset, dataset_version, mutationtype, tool,
                                                            approach, killtype, aggregation, tiebreak, formula)
                                                    code_entity_linenum_dfs.append(code_entity_linenum_df)
                                                except Exception as e:
                                                    error_message = f"Error occurred: {pid}-{version}-{dataset}-{dataset_version}-{mutationtype}-{tool}-{killtype}-{approach}-{aggregation}-{tiebreak}-{formula}: {e}"
                                                    logging.error(error_message)
                                                    print(error_message)
                                        
                                        # 基于并集的code_entity_linenum_df计算rank
                                        if len(code_entity_linenum_dfs) > 0:
                                            code_entity_linenum_df = pd.concat(code_entity_linenum_dfs)
                                            code_entity_linenum_df = code_entity_linenum_df.drop_duplicates().reset_index(drop=True)

                                            for mutationtype in MutationType:
                                                tools = Tool[mutationtype]
                                                for tool in tools:
                                                    try:
                                                        getRank(pid, f"{version}", granularity, dataset, dataset_version,  mutationtype, tool,
                                                                approach, killtype, aggregation, tiebreak, formula, 
                                                                code_entity_linenum_df=code_entity_linenum_df, fillna_strategy='fill_lower_than_min')
                                                    except Exception as e:
                                                        error_message = f"Error occurred: {pid}-{version}-{dataset}-{dataset_version}-{mutationtype}-{tool}-{killtype}-{approach}-{aggregation}-{tiebreak}-{formula}: {e}"
                                                        logging.error(error_message)
                                                        print(error_message)

                                                        # Defects4J/MergeSus/SusDRankAvg tool/FACombination appraoch/kill_type3 killtype /max a/Avg/Chart/1/Dstar.csv


# getRank("Chart",f"{i}","mBERT","Statement","Defects4J","NeuralMutation","FACombination","kill_type3","max","Dstar", "Avg")

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

    # init("Collections", ["25"])