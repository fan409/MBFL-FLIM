#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2-3_FLIM_Identification.py

Description: Identify Fault Localization Interference Mutants (FLIM) using Large Language Models.
             This step is inserted between Step 2 (Mutant Execution) and Step 3 (Kill Matrix Construction)
             to filter out mutants that may interfere with fault localization effectiveness.

Input: 
    MutantTestResult: MutantTestResult/Processed/$Project/{$Version}b
    Original Program: Dataset/Defects4J_Repo/$Project/{$Version}b
    Failing Tests: Dataset/FaultInfo/FailingTests/$Project/{$Version}b/failing_tests.json
    Mutant Repository: Mutant_Repo/Mutant_Repo_Processed/$Project/{$Version}b

Output: 
    FLIM Analysis Results: FLIMAnalysis/$Project/{$Version}b/flim_results.json
    Filtered Mutant List: FLIMAnalysis/$Project/{$Version}b/non_flim_mutants.json
    FLIM Report: FLIMAnalysis/$Project/{$Version}b/flim_analysis_report.txt
"""

from builtins import breakpoint
import os
import sys
import json
import pandas as pd
import numpy as np
import difflib
import logging
import subprocess
import requests
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import re

from Defects4JPyInterface import get_projects, get_versions
from STEnvConfigManager import get_pathConfig

pathConfig = get_pathConfig()
if pathConfig is None:
    raise ValueError("Please configure the environment path first.")

class FLIMConfig:
    """
    FLIM识别配置类,包含从runMutantFaultyFile-automulti.py硬编码的参数
    """
    
    # 硬编码的配置参数 (从runMutantFaultyFile-automulti.py提取) 
    DEFAULT_DATASET = "Defects4J"
    DEFAULT_DATASET_VERSION = "D4JCleanCD4J"  # 也可选择 "Defects4J_v2.0.0"
    DEFAULT_MUTATION_TYPE = "NeuralMutation"  # 也可选择 "NeuralMutation",TraditionalMutation
    DEFAULT_MUTATION_TOOL = "mBERT"  # 也可选择 "mbert"
    DEFAULT_IDENTIFICATION_ATTEMPTS = 5  # 每个变异体识别次数，默认5次
    
    # 重试机制配置参数
    DEFAULT_MAX_RETRIES_PER_ATTEMPT = 5  # 每次尝试的最大重试次数，默认5次
    DEFAULT_RETRY_DELAY = 1.0  # 重试间隔时间（秒），默认1秒
    DEFAULT_RETRY_BACKOFF_FACTOR = 1.5  # 重试延迟递增因子，默认1.5倍递增
    
    # 支持的项目列表
    SUPPORTED_PROJECTS = [
        "Chart", "Lang", "Math", "Closure", "Mockito", "Time",
        "Codec", "Cli", "Csv", "Gson", "JacksonCore", "JacksonXml",
        "Collections", "JacksonDatabind", "JxPath", "Jsoup", "Compress"
    ]
    
    def __init__(self, dataset=None, dataset_version=None, mutation_type=None, mutation_tool=None, 
                 identification_attempts=None, max_retries_per_attempt=None, retry_delay=None, retry_backoff_factor=None):
        """
        初始化配置
        
        Args:
            dataset (str, optional): 数据集名称,默认为DEFAULT_DATASET
            dataset_version (str, optional): 数据集版本,默认为DEFAULT_DATASET_VERSION
            mutation_type (str, optional): 变异类型,默认为DEFAULT_MUTATION_TYPE
            mutation_tool (str, optional): 变异工具,默认为DEFAULT_MUTATION_TOOL
            identification_attempts (int, optional): 每个变异体识别次数,默认为DEFAULT_IDENTIFICATION_ATTEMPTS
            max_retries_per_attempt (int, optional): 每次尝试的最大重试次数,默认为DEFAULT_MAX_RETRIES_PER_ATTEMPT
            retry_delay (float, optional): 重试间隔时间（秒）,默认为DEFAULT_RETRY_DELAY
            retry_backoff_factor (float, optional): 重试延迟递增因子,默认为DEFAULT_RETRY_BACKOFF_FACTOR
        """
        self.dataset = dataset or self.DEFAULT_DATASET
        self.dataset_version = dataset_version or self.DEFAULT_DATASET_VERSION
        self.mutation_type = mutation_type or self.DEFAULT_MUTATION_TYPE
        self.mutation_tool = mutation_tool or self.DEFAULT_MUTATION_TOOL
        self.identification_attempts = identification_attempts or self.DEFAULT_IDENTIFICATION_ATTEMPTS
        
        # 重试机制配置
        self.max_retries_per_attempt = max_retries_per_attempt or self.DEFAULT_MAX_RETRIES_PER_ATTEMPT
        self.retry_delay = retry_delay or self.DEFAULT_RETRY_DELAY
        self.retry_backoff_factor = retry_backoff_factor or self.DEFAULT_RETRY_BACKOFF_FACTOR
    
    def get_mutation_test_paths(self, project):
        """
        获取变异测试相关路径
        
        Args:
            project (str): 项目名称
            
        Returns:
            tuple: (D4J_Repo, MUTANT_REPO_DIR, MUTANT_TEST_RESULT_DIR, FLIM_ANALYSIS_DIR, FAULT_INFO_DIR)
        """
        if self.dataset != "Defects4J":
            raise ValueError("Invalid dataset name. Please use Defects4J.")
        
        # 设置D4J仓库路径
        if self.dataset_version == "Defects4J_v2.0.0":
            D4J_Repo = Path(pathConfig["D4J"]) / "project_repository"
        elif self.dataset_version == "D4JCleanCD4J":
            D4J_Repo = Path(pathConfig["D4JCleanCD4J"])
        else:
            raise ValueError(f"Unsupported dataset version: {self.dataset_version}")
        
        # 设置故障信息目录
        if self.dataset_version == "D4JCleanCD4J":
            if project in ["Collections", "JacksonDatabind", "JxPath"]:
                FAULT_INFO_DIR = Path(pathConfig["D4J"]) / "faultyLinePlus" / f"{project}FaultLine.txt"
            else:
                FAULT_INFO_DIR = Path(pathConfig["D4JClean"]) / "faultyLinePlus" / f"{project}FaultLine.txt"
        else:
            FAULT_INFO_DIR = Path(pathConfig["D4J"]) / "faultyLinePlus" / f"{project}FaultLine.txt"
        
        # 变异体仓库目录
        MUTANT_REPO_DIR = Path(pathConfig[self.mutation_type]) / self.mutation_tool / "MutantRepo" / self.dataset / self.dataset_version / "Mutant4FaultyFile"
        
        # 变异体原始测试结果目录
        MUTANT_TEST_RESULT_DIR = Path(pathConfig[f"{self.mutation_type}Result"]) / self.mutation_tool / self.dataset / self.dataset_version / "result4FaultFile"
        
        # FLIM分析结果目录
        FLIM_ANALYSIS_DIR = Path(pathConfig[f"{self.mutation_type}FLIMRecognitionResult"]) / self.mutation_tool / self.dataset / self.dataset_version / "FLIMRecognition4FaultFile_added"
        
        return D4J_Repo, MUTANT_REPO_DIR, MUTANT_TEST_RESULT_DIR, FLIM_ANALYSIS_DIR, FAULT_INFO_DIR

    def check_required_resources(self, project: str, version: str) -> Dict[str, Any]:
        """
        检查指定项目版本的必备资源目录是否存在
        
        Args:
            project (str): 项目名称
            version (str): 项目版本
            
        Returns:
            Dict[str, Any]: 检查结果，包含以下字段：
                - all_resources_available (bool): 所有资源是否都可用
                - missing_resources (List[str]): 缺失的资源列表
                - resource_status (Dict[str, Dict]): 每个资源的详细状态
                - project (str): 项目名称
                - version (str): 项目版本
        """
        try:
            # 获取所有路径
            (project_path_base, mutant_repo_path_base, 
             mutant_test_result_path_base, output_path_base, 
             fault_info_path_base) = self.get_mutation_test_paths(project)
            
            # 构建具体的项目版本路径
            project_path = project_path_base / project / f"{version}b"
            mutant_test_result_path = mutant_test_result_path_base / project / f"{version}b"
            mutant_repo_path = mutant_repo_path_base / project / f"{project.lower()}_{version}_buggy"
            fault_info_path = fault_info_path_base
            
            # 定义需要检查的资源
            resources_to_check = {
                "project_source": {
                    "path": project_path,
                    "description": f"项目源代码目录 ({project} {version}b)",
                    "required": True
                },
                "mutant_repository": {
                    "path": mutant_repo_path,
                    "description": f"变异体仓库目录 ({project.lower()}_{version}_buggy)",
                    "required": True
                },
                "mutant_test_results": {
                    "path": mutant_test_result_path,
                    "description": f"变异体测试结果目录 ({project} {version}b)",
                    "required": True
                },
                "fault_info": {
                    "path": fault_info_path,
                    "description": f"故障信息文件 ({project}FaultLine.txt)",
                    "required": True
                }
            }
            
            # 检查每个资源的状态
            resource_status = {}
            missing_resources = []
            
            for resource_name, resource_info in resources_to_check.items():
                path = resource_info["path"]
                exists = path.exists()
                is_accessible = False
                
                if exists:
                    try:
                        # 检查是否可访问（对于目录检查是否可列出，对于文件检查是否可读）
                        if path.is_dir():
                            list(path.iterdir())  # 尝试列出目录内容
                            is_accessible = True
                        elif path.is_file():
                            with open(path, 'r', encoding='utf-8') as f:
                                f.read(1)  # 尝试读取一个字符
                            is_accessible = True
                    except (PermissionError, OSError):
                        is_accessible = False
                
                resource_status[resource_name] = {
                    "path": str(path),
                    "exists": exists,
                    "accessible": is_accessible,
                    "description": resource_info["description"],
                    "required": resource_info["required"],
                    "available": exists and is_accessible
                }
                
                # 如果是必需资源且不可用，添加到缺失列表
                if resource_info["required"] and not (exists and is_accessible):
                    missing_resources.append(resource_name)
            
            # 判断所有必备资源是否都可用
            all_resources_available = len(missing_resources) == 0
            
            return {
                "all_resources_available": all_resources_available,
                "missing_resources": missing_resources,
                "resource_status": resource_status,
                "project": project,
                "version": version
            }
            
        except Exception as e:
            # 如果检查过程中出现异常，返回错误状态
            return {
                "all_resources_available": False,
                "missing_resources": ["检查过程出现异常"],
                "resource_status": {},
                "project": project,
                "version": version,
                "error": str(e)
            }

# 保持向后兼容的函数
def get_MutationTestPath(Dataset, DatasetVersion, MutationType, MutationTool, Project):
    """
    保持向后兼容的路径获取函数
    """
    config = FLIMConfig(Dataset, DatasetVersion, MutationType, MutationTool)
    D4J_Repo, MUTANT_REPO_DIR, MUTANT_TEST_RESULT_DIR, FLIM_ANALYSIS_DIR, FAULT_INFO_DIR = config.get_mutation_test_paths(Project)
    return D4J_Repo, MUTANT_REPO_DIR, MUTANT_TEST_RESULT_DIR

def numbered_UnifiedDiff(a, b, 
                        fromfile: str = '', tofile: str = '', 
                        old_start: int = 1, new_start: int = 1, 
                        lineterm: str = '\n', n: int = 3) -> List[str]:
    """
    给 unified_diff 的每一行加上旧/新行号,返回纯文本列表。
    格式: 
        -old_n | +new_n | 文本     # 上下文
        -old_n |        | 文本     # 删除行
              | +new_n | 文本     # 新增行
    """
    old_line = old_start
    new_line = new_start
    out: List[str] = []

    for raw in difflib.unified_diff(
            a, b, fromfile, tofile,
            fromfiledate='', tofiledate='',
            n=n, lineterm=lineterm):

        if raw.startswith(('---', '+++')):
            # out.append(raw)          # header 原样保留
            continue
        
        if raw.startswith('@@'):
            # 解析 hunk header 里的起始行号
            import re
            m = re.search(r'^@@ -(\d+)(?:,\d+)? \+(\d+)', raw)
            if m:
                old_line = int(m.group(1))
                new_line = int(m.group(2))
            out.append(raw)          # header 原样保留
            continue

        flag = raw[0] if raw else ' '                # ' ', '-', '+'
        content = raw[1:].rstrip('\n') if len(raw) > 1 else ''

        if flag == ' ':              # 上下文
            out.append(f'-{old_line:4} | +{new_line:4} | {content}')
            old_line += 1
            new_line += 1
        elif flag == '-':            # 删除
            out.append(f'-{old_line:4} |       | {content}')
            old_line += 1
        elif flag == '+':            # 新增
            out.append(f'      | +{new_line:4} | {content}')
            new_line += 1
        else:                        # 理论上不会走到
            out.append(raw)
    return out

class FLIMIdentifier:
    """
    Fault Localization Interference Mutant (FLIM) Identifier
    
    This class implements FLIM identification using Large Language Models
    to analyze mutants from a semantic perspective and identify those that
    may interfere with fault localization effectiveness.
    """
    
    def __init__(self, project: str, version: str, config: Optional[FLIMConfig] = None, model_config: Optional[Dict] = None, enable_resume: bool = True, batch_mode: bool = False, batch_processor=None):
        """
        Initialize FLIM Identifier
        
        Args:
            project (str): Defects4J project name
            version (str): Project version
            config (FLIMConfig, optional): FLIM配置对象,如果为None则使用默认配置
            model_config (Dict, optional): LLM configuration parameters
            enable_resume (bool, optional): 是否启用断点恢复功能，默认为True
            batch_mode (bool, optional): 是否为批处理模式，默认为False
            batch_processor: 批处理器实例，用于多级日志记录
        """
        self.project = project
        self.version = version
        self.config = config or FLIMConfig()  # 使用默认配置或传入的配置
        self.model_config = model_config or self._get_default_model_config()
        self.identification_attempts = self.config.identification_attempts  # 获取识别次数
        self.enable_resume = enable_resume  # 断点恢复功能开关
        self._batch_mode = batch_mode  # 批处理模式标志
        self._batch_processor = batch_processor  # 批处理器引用
        
        # Setup paths using the config
        (self.project_path_base, self.mutant_repo_path_base, 
         self.mutant_test_result_path_base, self.output_path_base, 
         self.fault_info_path_base) = self.config.get_mutation_test_paths(project)
        
        # Setup specific paths for this project and version
        self.project_path = self.project_path_base / project / f"{version}b"
        self.mutant_test_result_path = self.mutant_test_result_path_base / project / f"{version}b"
        self.mutant_repo_path = self.mutant_repo_path_base / project / f"{project.lower()}_{version}_buggy"
        self.fault_info_path = self.fault_info_path_base
        self.output_path = self.output_path_base / project / f"{version}b"
        
        # Ensure output directory exists
        self.output_path.mkdir(parents=True, exist_ok=True)
        
        # Setup mutant results directory
        self.mutant_results_path = self.output_path
        self.mutant_results_path.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        self._setup_logging()
        
        # Initialize multi-level logger references for warning/error propagation
        self._setup_multi_level_loggers()
        
        # Check required resources
        self.resource_check_result = self.config.check_required_resources(project, version)
        self.resources_available = self.resource_check_result["all_resources_available"]
        
        # Log resource check results
        if not self.resources_available:
            missing_resources = self.resource_check_result["missing_resources"]
            self.log_warning(f"缺失必备资源: {', '.join(missing_resources)}")
            for resource_name in missing_resources:
                if resource_name in self.resource_check_result["resource_status"]:
                    resource_info = self.resource_check_result["resource_status"][resource_name]
                    self.log_warning(f"  - {resource_info['description']}: {resource_info['path']}")
        else:
            self.logger.info("所有必备资源检查通过")
        
        # Initialize model components (placeholder for actual implementation)
        self.tokenizer = None
        self.model = None
        
    def _get_default_model_config(self) -> Dict:
        """Get default model configuration for ollama"""
        return {
            "model_name": "deepseek-r1:14b",  # Ollama model name
            "base_url": "http://127.0.0.1:11434",  # Ollama API endpoint
            "max_tokens": 4096,
            "temperature": 0.7,
            "top_p": 0.9,
            "stream": False,
            "timeout": 300  # Request timeout in seconds
        }
    
    def _setup_logging(self):
        """Setup logging configuration with hierarchical logging support"""
        # 创建项目版本级日志文件
        version_log_file = self.output_path / "flim_identification.log"
        
        # 创建独立的logger，避免全局配置冲突
        logger_name = f"flim.{self.project}.{self.version}"
        logger = logging.getLogger(logger_name)
        
        # 清除已有的handlers，避免重复日志
        logger.handlers.clear()
        logger.setLevel(logging.INFO)
        
        # 创建formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        # 项目版本级文件handler
        version_handler = logging.FileHandler(version_log_file)
        version_handler.setFormatter(formatter)
        version_handler.setLevel(logging.INFO)
        logger.addHandler(version_handler)
        
        # 控制台handler（仅在single模式下添加，避免批处理时重复输出）
        if not hasattr(self, '_batch_mode') or not self._batch_mode:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            console_handler.setLevel(logging.INFO)
            logger.addHandler(console_handler)
        
        # 防止日志向上传播到root logger
        logger.propagate = False
        
        self.logger = logger
    
    def _setup_multi_level_loggers(self):
        """设置多级日志记录器引用，用于warning和error的多级记录"""
        # 项目版本级logger（已在_setup_logging中设置）
        self.version_logger = self.logger
        
        # 项目级和批处理级logger引用（如果在批处理模式下且有batch_processor）
        if self._batch_mode and self._batch_processor:
            # 从batch_processor获取项目级logger
            if self.project in self._batch_processor.project_loggers:
                self.project_logger = self._batch_processor.project_loggers[self.project]
            else:
                self.project_logger = None
            
            # 从batch_processor获取批处理级logger
            self.batch_logger = self._batch_processor.batch_logger
        else:
            self.project_logger = None
            self.batch_logger = None
    
    def log_warning(self, message: str):
        """
        记录warning信息到所有相关级别的日志
        
        Args:
            message (str): 警告信息
        """
        # 项目版本级日志（始终记录）
        self.version_logger.warning(message)
        
        # 项目级日志（批处理模式下记录）
        if self.project_logger:
            self.project_logger.warning(f"[{self.project}-{self.version}] {message}")
        
        # 批处理级日志（批处理模式下记录）
        if self.batch_logger:
            self.batch_logger.warning(f"[{self.project}-{self.version}] {message}")
    
    def log_error(self, message: str):
        """
        记录error信息到所有相关级别的日志
        
        Args:
            message (str): 错误信息
        """
        # 项目版本级日志（始终记录）
        self.version_logger.error(message)
        
        # 项目级日志（批处理模式下记录）
        if self.project_logger:
            self.project_logger.error(f"[{self.project}-{self.version}] {message}")
        
        # 批处理级日志（批处理模式下记录）
        if self.batch_logger:
            self.batch_logger.error(f"[{self.project}-{self.version}] {message}")

    def create_mutant_result_folder(self, mutant_id: str) -> Path:
        """
        Create a result folder for a specific mutant
        
        Args:
            mutant_id (str): The mutant identifier
            
        Returns:
            Path: Path to the created mutant result folder
        """
        mutant_folder = self.mutant_results_path / mutant_id
        mutant_folder.mkdir(parents=True, exist_ok=True)
        return mutant_folder
    
    def get_next_result_filename(self, mutant_folder: Path, model_name: str, attempt_number: int = None) -> str:
        """
        Get the result filename for a mutant with specific attempt number
        
        Args:
            mutant_folder (Path): Path to the mutant result folder
            model_name (str): Name of the model used
            attempt_number (int, optional): Specific attempt number. If None, find next available number.
            
        Returns:
            str: Result filename
        """
        # Clean model name for filename
        clean_model_name = model_name.replace(":", "-").replace("/", "-")
        
        if attempt_number is not None:
            # Use specific attempt number
            return f"{clean_model_name}-result-{attempt_number}.json"
        else:
            # Find existing result files and get next number (legacy behavior)
            existing_files = list(mutant_folder.glob(f"{clean_model_name}-result-*.json"))
            
            # Extract numbers and find the next one
            numbers = []
            for file in existing_files:
                try:
                    # Extract number from filename like "model-result-1.json"
                    number_part = file.stem.split("-result-")[-1]
                    numbers.append(int(number_part))
                except (ValueError, IndexError):
                    continue
            
            next_number = max(numbers, default=0) + 1
            return f"{clean_model_name}-result-{next_number}.json"
    
    def save_mutant_result(self, mutant_id: str, result: Dict, attempt_number: int = None) -> Path:
        """
        Save individual mutant result to its dedicated folder
        
        Args:
            mutant_id (str): The mutant identifier
            result (Dict): The analysis result
            attempt_number (int, optional): Specific attempt number for filename
            
        Returns:
            Path: Path to the saved result file
        """
        # Create mutant folder
        mutant_folder = self.create_mutant_result_folder(mutant_id)
        
        # Get filename
        model_name = self.model_config.get("model_name", "unknown-model")
        filename = self.get_next_result_filename(mutant_folder, model_name, attempt_number)
        
        # Save result
        result_file = mutant_folder / filename
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Saved mutant result to: {result_file}")
        return result_file

    def is_mutant_analysis_completed(self, mutant_id: str) -> bool:
        """
        Check if a mutant has completed all identification attempts
        
        Args:
            mutant_id (str): The mutant identifier
            
        Returns:
            bool: True if all identification attempts are completed, False otherwise
        """
        if not self.enable_resume:
            return False
            
        try:
            # Get mutant result folder
            mutant_folder = self.mutant_results_path / mutant_id
            if not mutant_folder.exists():
                return False
            
            # Get model name for filename pattern
            model_name = self.model_config.get("model_name", "unknown-model")
            clean_model_name = model_name.replace(":", "-").replace("/", "-")
            
            # Check if all required attempts exist
            for attempt in range(1, self.identification_attempts + 1):
                expected_filename = f"{clean_model_name}-result-{attempt}.json"
                result_file = mutant_folder / expected_filename
                
                if not result_file.exists():
                    self.logger.debug(f"Missing result file for mutant {mutant_id}, attempt {attempt}: {result_file}")
                    return False
                
                # Optionally, verify the file is valid JSON and contains expected data
                try:
                    with open(result_file, 'r', encoding='utf-8') as f:
                        result_data = json.load(f)
                        # Basic validation - check if it has required fields
                        if not isinstance(result_data, dict) or 'mutant_id' not in result_data:
                            self.logger.debug(f"Invalid result file for mutant {mutant_id}, attempt {attempt}: {result_file}")
                            return False
                except (json.JSONDecodeError, IOError) as e:
                    self.logger.debug(f"Error reading result file for mutant {mutant_id}, attempt {attempt}: {e}")
                    return False
            
            self.logger.debug(f"Mutant {mutant_id} has completed all {self.identification_attempts} identification attempts")
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking completion status for mutant {mutant_id}: {e}")
            return False

    def save_progress(self, current_mutant_index: int, total_mutants: int, completed_mutants: List[str], skipped_mutants: int):
        """
        Save current progress for breakpoint recovery
        
        Args:
            current_mutant_index (int): Current mutant index being processed
            total_mutants (int): Total number of mutants
            completed_mutants (List[str]): List of completed mutant IDs
            skipped_mutants (int): Number of skipped mutants
        """
        if not self.enable_resume:
            return
            
        try:
            progress_data = {
                "timestamp": datetime.now().isoformat(),
                "project": self.project,
                "version": self.version,
                "current_mutant_index": current_mutant_index,
                "total_mutants": total_mutants,
                "completed_mutants": completed_mutants,
                "skipped_mutants": skipped_mutants,
                "identification_attempts": self.identification_attempts,
                "model_config": self.model_config
            }
            
            progress_file = self.output_path / "progress.json"
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump(progress_data, f, indent=2, ensure_ascii=False)
                
            self.logger.debug(f"Progress saved: {current_mutant_index}/{total_mutants} mutants processed")
            
        except Exception as e:
            self.logger.error(f"Error saving progress: {e}")

    def load_progress(self) -> Optional[Dict]:
        """
        Load previous progress for breakpoint recovery
        
        Returns:
            Dict: Progress data if exists, None otherwise
        """
        if not self.enable_resume:
            return None
            
        try:
            progress_file = self.output_path / "progress.json"
            if not progress_file.exists():
                return None
                
            with open(progress_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
                
            # Validate progress data
            if (progress_data.get("project") == self.project and 
                progress_data.get("version") == self.version):
                self.logger.info(f"Loaded previous progress: {progress_data.get('current_mutant_index', 0)}/{progress_data.get('total_mutants', 0)} mutants processed")
                return progress_data
            else:
                self.logger.warning("Progress file exists but doesn't match current project/version")
                return None
                
        except Exception as e:
            self.logger.error(f"Error loading progress: {e}")
            return None

    def load_model(self):
        """
        Load and test the Ollama model for FLIM identification
        """
        try:
            import requests
            
            # Test ollama service connectivity
            base_url = self.model_config["base_url"]
            model_name = self.model_config["model_name"]
            
            # Check if ollama service is running
            try:
                response = requests.get(f"{base_url}/api/version", timeout=5)
                if response.status_code != 200:
                    raise Exception(f"Ollama service not responding: {response.status_code}")
            except requests.exceptions.RequestException as e:
                raise Exception(f"Cannot connect to Ollama service at {base_url}: {e}")
            
            # Check if the model is available
            try:
                response = requests.get(f"{base_url}/api/tags", timeout=10)
                if response.status_code == 200:
                    models_data = response.json()
                    available_models = [model['name'] for model in models_data.get('models', [])]
                    if model_name not in available_models:
                        self.logger.warning(f"Model {model_name} not found in available models: {available_models}")
                        self.logger.info(f"Attempting to pull model {model_name}...")
                        # Note: Model pulling should be done manually via: ollama pull {model_name}
                        # For now, we'll continue and let the API call handle the error
                else:
                    self.logger.warning(f"Could not retrieve model list: {response.status_code}")
            except Exception as e:
                self.logger.warning(f"Could not check available models: {e}")
            
            # Test model with a simple query
            test_payload = {
                "model": model_name,
                "prompt": "Hello, this is a test. Please respond with 'Test successful'.",
                "stream": False
            }
            
            response = requests.post(
                f"{base_url}/api/generate",
                json=test_payload,
                timeout=self.model_config.get("timeout", 30)
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'response' in result:
                    self.logger.info(f"Ollama model {model_name} loaded and tested successfully")
                    self.logger.debug(f"Test response: {result['response'][:100]}...")
                    return True
                else:
                    raise Exception(f"Unexpected response format: {result}")
            else:
                raise Exception(f"Model test failed: {response.status_code} - {response.text}")
                
        except Exception as e:
            self.logger.error(f"Failed to load Ollama model: {e}")
            return False
    

    
    def get_mutant_id_from_path(self, mutant_path: str) -> str:
        """
        Generate mutant_id from mutant file path
        
        Args:
            mutant_path (str): Full path to the mutant file
            
        Returns:
            str: Generated mutant_id in format like source-org-jfree-data-general-DatasetUtilities-81-3
        """
        try:
            mutant_path = Path(mutant_path)
            # Find the position after project/version (e.g., Chart/2b)
            mutant_repo_processed = self.mutant_repo_path
            src_start_pos = len(mutant_repo_processed.parts)
            
            # Extract path parts after the project/version directory, excluding the filename
            path_parts = mutant_path.parts[src_start_pos:-1]
            
            # Join with '-' to create mutant_id
            mutant_id = "-".join(path_parts)
            
            self.logger.debug(f"Generated mutant_id: {mutant_id} from path: {mutant_path}")
            return mutant_id
            
        except Exception as e:
            self.logger.error(f"Error generating mutant_id from path {mutant_path}: {e}")
            return f"error_mutant_id_{Path(mutant_path).stem}"

    def get_original_file_path(self, mutant_path: str) -> Path:
        """
        Get the original file path corresponding to a mutant
        
        Args:
            mutant_path (str): Path to the mutant file
            
        Returns:
            Path: Path to the original file
        """
        try:
            mutant_path = Path(mutant_path)
            mutant_repo_processed = self.mutant_repo_path
            src_start_pos = len(mutant_repo_processed.parts)
            
            # Extract relative path from mutant repo to the Java file (excluding mutation directories)
            relative_parts = mutant_path.parts[src_start_pos:-3]  # Remove last 3 parts (line/mutation/filename)
            relative_path = Path(*relative_parts).with_suffix('.java')
            
            # Construct original file path
            original_path = self.project_path / relative_path
            
            self.logger.debug(f"Original file path: {original_path} for mutant: {mutant_path}")
            return original_path
            
        except Exception as e:
            self.logger.error(f"Error getting original file path for mutant {mutant_path}: {e}")
            return None

    def get_mutant_code_diff(self, mutant_path: str) -> str:
        """
        Get the code difference between original and mutant
        
        Args:
            mutant_path (str): Path to the mutant file
            
        Returns:
            str: Code diff information
        """
        try:
            mutant_path = Path(mutant_path)
            original_path = self.get_original_file_path(mutant_path)
            
            if not original_path or not original_path.exists():
                return f"Original file not found for mutant {mutant_path}"
            
            if not mutant_path.exists():
                return f"Mutant file not found: {mutant_path}"
            
            # Read original and mutant files
            with open(original_path, 'r', encoding='utf-8') as f:
                original_lines = f.readlines()
            
            with open(mutant_path, 'r', encoding='utf-8') as f:
                mutant_lines = f.readlines()
            
            # Generate numbered unified diff
            diff = numbered_UnifiedDiff(
                original_lines, 
                mutant_lines,
                fromfile=f"original/{original_path.name}",
                tofile=f"mutant/{mutant_path.name}",
                old_start=1,
                new_start=1,
                lineterm=''
            )
            
            if diff:
                return '\n'.join(diff)
            else:
                return "No differences found between original and mutant"
                
        except Exception as e:
            self.logger.error(f"Error getting code diff for mutant {mutant_path}: {e}")
            return f"Error retrieving code diff: {e}"

    def get_original_program_context(self, mutant_path: str) -> str:
        """
        Get the original program context around the mutation location
        
        Args:
            mutant_path (str): Path to the mutant file
            
        Returns:
            str: Original program context
        """
        try:
            original_path = self.get_original_file_path(mutant_path)
            
            if not original_path or not original_path.exists():
                return f"Original file not found for mutant {mutant_path}"
            
            # Read the original file
            with open(original_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
            
            # Extract mutation location (line number)
            mutant_id = self.get_mutant_id_from_path(mutant_path)
            mutation_line = self.get_mutation_location(mutant_id)
            
            if mutation_line > 0:
                lines = original_content.split('\n')
                # Get context around the mutation line (±5 lines)
                start_line = max(0, mutation_line - 6)  # -1 for 0-based indexing, -5 for context
                end_line = min(len(lines), mutation_line + 5)
                
                context_lines = []
                for i in range(start_line, end_line):
                    prefix = ">>> " if i == mutation_line - 1 else "    "
                    context_lines.append(f"{prefix}{i+1:4d}: {lines[i]}")
                
                return '\n'.join(context_lines)
            else:
                # If we can't determine the line number, return the whole file (truncated)
                lines = original_content.split('\n')
                if len(lines) > 50:
                    return '\n'.join(lines[:50]) + f"\n... (truncated, total {len(lines)} lines)"
                else:
                    return original_content
                    
        except Exception as e:
            self.logger.error(f"Error getting original program context for mutant {mutant_path}: {e}")
            return f"Error retrieving original program context: {e}"

    def get_mutation_location(self, mutant_id: str) -> int:
        """
        Get the mutation location (line number) from mutant_id
        
        Args:
            mutant_id (str): Mutant identifier
            
        Returns:
            int: Line number where mutation occurred
        """
        try:
            # Split mutant_id by '-' and get the second-to-last integer
            parts = mutant_id.split('-')
            if len(parts) >= 2:
                # Get the second-to-last part and convert to int
                line_number = int(parts[-2])
                return line_number
            else:
                self.logger.warning(f"Cannot extract line number from mutant_id: {mutant_id}")
                return -1
                
        except (ValueError, IndexError) as e:
            self.logger.error(f"Error extracting mutation location from mutant_id {mutant_id}: {e}")
            return -1

    def parse_failing_tests_file(self, file_path: Path) -> Dict:
        """
        Parse failing tests file and extract test information with complete stack traces
        Based on the original file format from mutant test execution
        
        Format: 
        --- org.jfree.chart.junit.AreaChartTests::testDrawWithNullInfo
        java.lang.ArrayIndexOutOfBoundsException: -1
            at org.jfree.data.general.DatasetUtilities.createCategoryDataset(DatasetUtilities.java:109)
            at org.jfree.chart.junit.AreaChartTests.createAreaChart(AreaChartTests.java:77)
            ...
        
        Args:
            file_path (Path): Path to the failing tests file
            
        Returns:
            Dict: JSON格式的失败测试信息,以failing_test_name为外层key,值为包含error_type、error_message、stack_trace的字典
        """
        try:
            if not file_path.exists():
                return {}
            
            failing_tests = {}
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if not content.strip():
                return {}
            
            # Split content by test cases
            test_blocks = content.split('--- ')
            
            for block in test_blocks[1:]:  # Skip first empty block
                lines = block.split('\n')
                if len(lines) < 2:
                    continue
                
                # First line is the test name
                test_name_line = lines[0].strip()
                failing_test_name = test_name_line.replace('::', '#')
                
                # Second line is the error message line
                if len(lines) >= 2:
                    error_message = lines[1].strip()
                    
                    # Extract error type from error message
                    error_type = error_message
                    if ':' in error_message:
                        error_type = error_message.split(':')[0].strip()
                    elif 'Exception' in error_message or 'Error' in error_message:
                        # Handle cases like just "NullPointerException" without colon
                        error_type = error_message.split()[0] if error_message.split() else error_message
                else:
                    error_message = "Unknown error"
                    error_type = "Unknown"
                
                # Remaining lines are the stack trace
                stack_trace_lines = lines[2:] if len(lines) > 2 else []
                stack_trace = '\n'.join(line.rstrip() for line in stack_trace_lines if line.strip())
                
                # 以JSON格式组织,以failing_test_name为外层key
                failing_tests[failing_test_name] = {
                    'error_type': error_type,
                    'error_message': error_message,
                    'stack_trace': stack_trace
                }
            
            return failing_tests
            
        except Exception as e:
            self.logger.error(f"Error parsing failing tests file {file_path}: {e}")
            return {}

    def parse_failing_tests_json(self, file_path: Path) -> Dict:
        """
        Parse failing tests from JSON file (processed by 2-2_MutantTestResultProcess.py)
        
        Args:
            file_path (Path): Path to the JSON file
            
        Returns:
            Dict: Dictionary of failing test information with failing_test_name as key
        """
        try:
            if not file_path.exists():
                return {}
            
            with open(file_path, 'r', encoding='utf-8') as f:
                test_data = json.load(f)
            
            failing_tests = {}
            
            # Convert JSON format to our new format
            for test_name, test_info in test_data.items():
                # Extract error type from the JSON structure
                error_type = test_info.get('type3', 'Unknown')
                
                failing_tests[test_name] = {
                    'error_type': error_type,
                    'error_message': error_type,
                    'stack_trace': ''  # JSON format doesn't include stack trace
                }
            
            self.logger.info(f"Parsed {len(failing_tests)} failing tests from {file_path}")
            return failing_tests
            
        except Exception as e:
            self.logger.error(f"Error parsing JSON failing tests file {file_path}: {e}")
            return {}

    def load_original_failing_tests(self) -> Dict:
        """Load original failing test information"""
        try:
            # Try to load from the original program's failing_tests file
            original_failing_tests_file = self.project_path / "failing_tests"
            
            if original_failing_tests_file.exists():
                return self.parse_failing_tests_file(original_failing_tests_file)
            
            # Alternative: try to load from fault info directory
            fault_info_file = self.fault_info_path / "failing_tests"
            if fault_info_file.exists():
                return self.parse_failing_tests_file(fault_info_file)
            
            # # If no file found, try JSON format
            # json_file = self.fault_info_path / "failing_tests.json"
            # if json_file.exists():
            #     with open(json_file, 'r') as f:
            #         data = json.load(f)
            #         # Handle both old List[Dict] and new Dict formats
            #         if isinstance(data, list):
            #             # Convert old format to new Dict format
            #             new_format = {}
            #             for item in data:
            #                 test_name = item.get('test_name', 'Unknown')
            #                 new_format[test_name] = {
            #                     'error_type': item.get('error_type', 'Unknown'),
            #                     'error_message': item.get('error_message', 'No error message'),
            #                     'stack_trace': item.get('stack_trace', '')
            #                 }
            #             return new_format
            #         return data
            
            # Fallback: try alternative dataset paths based on project type
            self.logger.info(f"Trying alternative dataset paths for {self.project} {self.version}")
            
            # Define special projects that use D4J path
            special_projects = ["Collections", "JacksonDatabind", "JxPath"]
            
            if self.project in special_projects:
                # Use D4J path for special projects
                alternative_base_path = Path("/home/rs/WorkEx/Projects/SoftwareTesting/DataSet/Defects4J/D4J/FaultInfo/FailingTest/FailingTest4ProjectVersions")
                alternative_path = alternative_base_path / self.project / f"{self.version}b"
            else:
                # Use D4JClean path for other projects
                alternative_base_path = Path("/home/rs/WorkEx/Projects/SoftwareTesting/DataSet/Defects4J/D4JClean/failingTestOutput")
                alternative_path = alternative_base_path / self.project / f"{self.version}b"
            
            self.logger.info(f"Checking alternative path: {alternative_path}")
            
            # Try to find failing_tests file in alternative path
            alternative_failing_tests_file = alternative_path / "failing_tests"
            if alternative_failing_tests_file.exists():
                self.logger.info(f"Found failing_tests file at alternative path: {alternative_failing_tests_file}")
                return self.parse_failing_tests_file(alternative_failing_tests_file)
            
            # # Try JSON format in alternative path
            # alternative_json_file = alternative_path / "failing_tests.json"
            # if alternative_json_file.exists():
            #     self.logger.info(f"Found failing_tests.json file at alternative path: {alternative_json_file}")
            #     with open(alternative_json_file, 'r') as f:
            #         data = json.load(f)
            #         # Handle both old List[Dict] and new Dict formats
            #         if isinstance(data, list):
            #             # Convert old format to new Dict format
            #             new_format = {}
            #             for item in data:
            #                 test_name = item.get('test_name', 'Unknown')
            #                 new_format[test_name] = {
            #                     'error_type': item.get('error_type', 'Unknown'),
            #                     'error_message': item.get('error_message', 'No error message'),
            #                     'stack_trace': item.get('stack_trace', '')
            #                 }
            #             return new_format
            #         return data
            
            self.logger.warning(f"No original failing tests found for {self.project} {self.version} in any location")
            return {}
            
        except Exception as e:
            self.logger.error(f"Error loading original failing tests: {e}")
            return {}

    def get_mutant_failing_tests(self, mutant_id: str) -> Dict:
        """
        Get failing test results for a specific mutant by mutant_id
        
        Args:
            mutant_id (str): Mutant identifier
            
        Returns:
            Dict: Dictionary of failing tests with test names as keys, same format as original failing tests
        """
        try:
            # Construct the path to the mutant test result file
            mutant_test_file = self.mutant_test_result_path / mutant_id
            
            if not mutant_test_file.exists():
                self.logger.debug(f"No test result file found for mutant {mutant_id}: {mutant_test_file}")
                return {}
            
            # Parse the failing tests file and return directly
            failing_tests = self.parse_failing_tests_file(mutant_test_file)
            
            self.logger.debug(f"Loaded {len(failing_tests)} failing tests for mutant {mutant_id}")
            return failing_tests
            
        except Exception as e:
            self.logger.error(f"Error loading test results for mutant {mutant_id}: {e}")
            return {}

    def find_mutant_files(self) -> List[str]:
        """
        Find all mutant files in the mutant repository
        
        Returns:
            List[str]: List of mutant file paths
        """
        try:
            mutant_files = []
            
            # Use find command to locate all Java files in the mutant repository
            find_command = f"find {self.mutant_repo_path} -type f -name '*.java'"
            result = subprocess.run(find_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if result.returncode == 0:
                for file_path in result.stdout.strip().split('\n'):
                    if file_path:
                        mutant_files.append(file_path)
            else:
                self.logger.error(f"Error finding mutant files: {result.stderr}")
            
            self.logger.info(f"Found {len(mutant_files)} mutant files")
            return mutant_files
            
        except Exception as e:
            self.logger.error(f"Error finding mutant files: {e}")
            return []

    def sort_mutant_files(self, mutant_files: List[str]) -> List[str]:
        """
        Sort mutant files based on prefix, line number, and line index extracted from mutant_id
        
        Args:
            mutant_files (List[str]): List of mutant file paths
            
        Returns:
            List[str]: Sorted list of mutant file paths
        """
        try:
            def extract_sort_key(mutant_path: str):
                """
                Extract sorting key from mutant path
                Returns tuple: (prefix, line_number, line_index)
                """
                try:
                    mutant_id = self.get_mutant_id_from_path(mutant_path)
                    parts = mutant_id.split('-')
                    
                    if len(parts) >= 2:
                        # Extract line number (second to last part) and line index (last part)
                        line_index = int(parts[-1])  # Last part: line index
                        line_number = int(parts[-2])  # Second to last part: line number
                        # Prefix is everything except the last two parts
                        prefix = '-'.join(parts[:-2])
                        
                        return (prefix, line_number, line_index)
                    else:
                        # Fallback: use the entire mutant_id as prefix
                        return (mutant_id, 0, 0)
                        
                except (ValueError, IndexError) as e:
                    self.logger.warning(f"Error extracting sort key from {mutant_path}: {e}")
                    # Fallback: use the path as is
                    return (mutant_path, 0, 0)
            
            # Sort the mutant files
            sorted_files = sorted(mutant_files, key=extract_sort_key)
            
            self.logger.info(f"Sorted {len(sorted_files)} mutant files by prefix, line number, and line index")
            return sorted_files
            
        except Exception as e:
            self.logger.error(f"Error sorting mutant files: {e}")
            # Return original list if sorting fails
            return mutant_files

    def filter_test_framework_traces(self, stack_trace: str) -> str:
        """
        Filter out test framework traces from stack trace
        
        Args:
            stack_trace (str): Original stack trace
            
        Returns:
            str: Filtered stack trace
        """
        if not stack_trace:
            return ""
        
        lines = stack_trace.split('\n')
        filtered_lines = []
        
        # Common test framework patterns to filter out
        framework_patterns = [
            'org.junit.',
            'junit.',
            'org.testng.',
            'org.apache.maven.',
            'sun.reflect.',
            'java.lang.reflect.',
            'org.eclipse.jdt.',
            'org.gradle.',
            'com.intellij.'
        ]
        
        for line in lines:
            line = line.strip()
            filtered_lines.append(line)
            # if line and not any(pattern in line for pattern in framework_patterns):
            #     filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)

    def analyze_test_status_changes(self, original_failing_tests: Dict, 
                                  mutant_failing_tests: Dict) -> Dict:
        """
        Analyze test status changes between original and mutant
        
        Args:
            original_failing_tests (Dict): Original failing tests with failing_test_name as key
            mutant_failing_tests (Dict): Mutant failing tests with failing_test_name as key
            
        Returns:
            Dict: Test status change analysis with test names as keys
        """
        try:
            # Get sets of test names for comparison
            original_failing_names = set(original_failing_tests.keys())
            mutant_failing_names = set(mutant_failing_tests.keys())
            
            test_changes = {}
            
            # Case 1: Originally failing tests that now pass in mutant
            for test_name in original_failing_names - mutant_failing_names:
                original_test = original_failing_tests[test_name]
                test_changes[test_name] = {
                    'status_change': 'originally_failing_now_passing',
                    'original_error': original_test.get('error_message', ''),
                    'original_stack_trace': original_test.get('stack_trace', ''),
                    'error_message_diff': None,
                    'stack_trace_diff': None
                }
            
            # Case 2: Originally passing tests that now fail in mutant
            for test_name in mutant_failing_names - original_failing_names:
                mutant_test = mutant_failing_tests[test_name]
                test_changes[test_name] = {
                    'status_change': 'originally_passing_now_failing',
                    'original_error': None,
                    'original_stack_trace': None,
                    'mutant_error': mutant_test.get('error_message', ''),
                    'mutant_stack_trace': mutant_test.get('stack_trace', ''),
                    'error_message_diff': None,
                    'stack_trace_diff': None
                }
            
            # Cases 3, 4, 5: Tests that fail in both original and mutant
            for test_name in original_failing_names & mutant_failing_names:
                original_test = original_failing_tests[test_name]
                mutant_test = mutant_failing_tests[test_name]
                
                original_error = original_test.get('error_message', '')
                mutant_error = mutant_test.get('error_message', '')
                original_stack = self.filter_test_framework_traces(original_test.get('stack_trace', ''))
                mutant_stack = self.filter_test_framework_traces(mutant_test.get('stack_trace', ''))
                
                # Check if error messages are different
                error_changed = original_error != mutant_error
                stack_changed = original_stack != mutant_stack
                
                if error_changed and stack_changed:
                    # Case 2: Both error message and stack trace changed
                    test_changes[test_name] = {
                        'status_change': 'failing_both_error_and_stack_changed',
                        'original_error': original_error,
                        'mutant_error': mutant_error,
                        'original_stack_trace': original_stack,
                        'mutant_stack_trace': mutant_stack,
                        'error_message_diff': self.get_text_diff(original_error, mutant_error),
                        'stack_trace_diff': self.get_text_diff(original_stack, mutant_stack)
                    }
                elif error_changed and not stack_changed:
                    # Case 3: Only error message changed
                    test_changes[test_name] = {
                        'status_change': 'failing_both_error_changed_only',
                        'original_error': original_error,
                        'mutant_error': mutant_error,
                        'original_stack_trace': original_stack,
                        'mutant_stack_trace': mutant_stack,
                        'error_message_diff': self.get_text_diff(original_error, mutant_error),
                        'stack_trace_diff': None
                    }
                elif not error_changed and stack_changed:
                    # Case 4: Only stack trace changed
                    test_changes[test_name] = {
                        'status_change': 'failing_both_stack_changed_only',
                        'original_error': original_error,
                        'mutant_error': mutant_error,
                        'original_stack_trace': original_stack,
                        'mutant_stack_trace': mutant_stack,
                        'error_message_diff': None,
                        'stack_trace_diff': self.get_text_diff(original_stack, mutant_stack)
                    }
                else:
                    # Case 5: No significant change
                    test_changes[test_name] = {
                        'status_change': 'failing_both_no_significant_change',
                        'original_error': original_error,
                        'mutant_error': mutant_error,
                        'original_stack_trace': original_stack,
                        'mutant_stack_trace': mutant_stack,
                        'error_message_diff': None,
                        'stack_trace_diff': None
                    }
            
            return test_changes
            
        except Exception as e:
            self.logger.error(f"Error analyzing test status changes: {e}")
            return {}

    def get_text_diff(self, text1: str, text2: str) -> str:
        """
        Get text difference between two strings
        
        Args:
            text1 (str): Original text
            text2 (str): Modified text
            
        Returns:
            str: Text diff
        """
        try:
            lines1 = text1.split('\n') if text1 else []
            lines2 = text2.split('\n') if text2 else []
            
            diff = list(difflib.unified_diff(
                lines1, lines2,
                fromfile='original',
                tofile='mutant',
                lineterm=''
            ))
            
            return '\n'.join(diff) if diff else "No differences"
            
        except Exception as e:
            return f"Error computing diff: {e}"

    def generate_flim_prompt(self, mutant_id: str, mutation_location: str, 
                           original_program: str, original_failing_info: Dict,
                           mutant_code_diff: str, mutant_test_changes_info: Dict,
                           custom_prompt: str = "", output_format: str = "",
                           mutant_info_only: bool = False) -> str:
        """
        Generate prompt for LLM to analyze FLIM characteristics
        
        Args:
            mutant_id (str): Mutant identifier
            mutation_location (str): Location of the mutation
            original_program (str): Original program context
            original_failing_info (Dict): Original failing test information
            mutant_code_diff (str): Code difference between original and mutant
            mutant_test_changes_info (Dict): Test status changes information
            custom_prompt (str, optional): Custom prompt template. If empty, uses default prompt. Defaults to "".
            output_format (str, optional): Custom output format specification. If empty, uses default format. Defaults to "".
            mutant_info_only (bool, optional): If True, returns only mutant information without base prompt and output format. Defaults to False.
            
        Returns:
            str: Generated prompt for LLM
        """

        # Construct mutant information section
        mutant_info = f"""# Input Format
The analysis requires the following input structure:
- Mutant ID: {mutant_id}

- Mutation Location: Line {mutation_location}

- Original Program Context:
{original_program}

- Original Failing Tests Information:
{original_failing_info}

- Mutant Code Changes:
{mutant_code_diff}

- Mutant Failing Tests Information:
{mutant_test_changes_info}"""

        # If only mutant info is requested, return it directly
        if mutant_info_only:
            return mutant_info

        # Use custom prompt if provided, otherwise use default prompt
        if custom_prompt:
            base_prompt = custom_prompt
        else:
            base_prompt = """我正在尝试通过变异分析的方法进行程序错误定位任务。

现在我面临一个错误的程序,这错误的程序导致部分测试用例失败。我希望找到这个程序中导致测试失败的原因,这个错误可能简单,可能复杂,也可能是遗漏错误 (由于代码缺失导致的测试失败) 。

我使用变异工具对程序进行了大量变异并对所有变异体执行了测试。
在这些变异体中,我需要逐个分析每个 导致部分或者全部 原本失败测试用例 结果发生变化 (包括从失败变为通过、以及虽然依旧是失败,但是其 报错信息 或者 堆栈信息 发生了变化)  的 变异体。因为这些变异体改变了至少一个 原错误程序 在 原本失败测试用例 上的 测试行为变化,说明 其应该 从现象上 与 原错误程序 的 错误 有关系。 

但是这并不足够,我希望你进一步分析 这个变异体究竟是 改变了原本错误程序 的 实际错误位置 及其 前后两行的代码 (这意味着 变异体植入的错误 可能 从根本上影响了错误,从而能够指示错误位置) ,还是 仅仅是影响了原本错误程序的测试行为特征,却在代码位置上与 原本程序的实际错误代码相距较远 (这意味着会误导我们关注不必要的代码) 。

我将为提供: 变异体的变异行 (Mutation Location,并不意味着这一行是原本程序错误的实际位置) 、变异体的代码上下文 (Original Program Context,使用>>>标注了变异体所在行号,但是变异体的上下文代码不一定包含原本程序的实际错误) 、原本程序失败测试的信息 (Original Failing Tests Information) 、变异体与原错误程序的diff (Mutant Code Changes,包含少量变异位置上下文) 、变异体测试结果与原错误程序的失败测试用例的diff (Mutant Failing Tests Information) 。

请你帮我根据变异体的信息判断一下,这个变异体是否可能位于程序原始错误代码行及其前后两行。"""

        # Use custom output format if provided, otherwise use default format
        if output_format:
            output_section = output_format
        else:
            output_section = f"""## Output Format
Only return a response that can be parsed by JSON, without any other content. The format is as follows:
```json
{{
    "mutant_id": "{mutant_id}",
    "is_fault_adjacent": bool (True or False)
}}
```"""

        # Construct complete prompt
        prompt = f"""{base_prompt}

{mutant_info}

{output_section}"""
        
        return prompt

    def query_llm(self, prompt: str) -> Optional[Dict]:
        """
        Query the Ollama Large Language Model with the given prompt
        
        Args:
            prompt (str): Input prompt for the LLM
            
        Returns:
            Optional[Dict]: LLM response parsed as dictionary with token statistics
        """
        try:
            import requests
            import json
            import re
            
            base_url = self.model_config["base_url"]
            model_name = self.model_config["model_name"]
            
            # Prepare the request payload
            payload = {
                "model": model_name,
                "prompt": prompt,
                "stream": self.model_config.get("stream", False),
                "options": {
                    "temperature": self.model_config.get("temperature", 0.7),
                    "top_p": self.model_config.get("top_p", 0.9),
                    "num_predict": self.model_config.get("max_tokens", 512)
                }
            }
            
            self.logger.debug(f"Sending request to Ollama API: {base_url}/api/generate")
            self.logger.debug(f"Using model: {model_name}")
            
            # Make the API request
            response = requests.post(
                f"{base_url}/api/generate",
                json=payload,
                timeout=self.model_config.get("timeout", 300)
            )
            
            if response.status_code != 200:
                self.logger.error(f"Ollama API request failed: {response.status_code} - {response.text}")
                return None
            
            # Parse the response
            result = response.json()
            
            if 'response' not in result:
                self.logger.error(f"Unexpected response format from Ollama: {result}")
                return None
            
            llm_response = result['response'].strip()
            self.logger.debug(f"Raw LLM response: {llm_response[:200]}...")
            
            # Extract token statistics from Ollama response
            token_stats = self._extract_token_statistics(result, prompt)
            
            # Try to extract JSON from the response
            try:
                # Look for JSON content between ```json and ``` or just parse the response directly
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', llm_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    # Try to find JSON object in the response
                    json_match = re.search(r'\{[^{}]*"mutant_id"[^{}]*\}', llm_response, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                    else:
                        # Fallback: try to parse the entire response as JSON
                        json_str = llm_response
                
                parsed_response = json.loads(json_str)
                
                # Validate the response format
                if "mutant_id" in parsed_response and "is_fault_adjacent" in parsed_response:
                    self.logger.debug(f"Successfully parsed LLM response: {parsed_response}")
                    
                    # Calculate is_flim based on is_fault_adjacent (following batch_analysis.py logic)
                    is_fault_adjacent = parsed_response.get("is_fault_adjacent", False)
                    is_flim = not is_fault_adjacent
                    
                    # Return response with both fields and token statistics
                    return {
                        "mutant_id": parsed_response.get("mutant_id", "unknown"),
                        "is_fault_adjacent": is_fault_adjacent,
                        "is_flim": is_flim,
                        "raw_response": llm_response,
                        "token_statistics": token_stats
                    }
                else:
                    self.logger.warning(f"LLM response missing required fields: {parsed_response}")
                    # Return a fallback response with the available data
                    return {
                        "mutant_id": parsed_response.get("mutant_id", "unknown"),
                        "is_fault_adjacent": parsed_response.get("is_fault_adjacent", False),
                        "is_flim": not parsed_response.get("is_fault_adjacent", False),
                        "raw_response": llm_response,
                        "token_statistics": token_stats
                    }
                    
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse LLM response as JSON: {e}")
                self.logger.error(f"Raw response: {llm_response}")
                
                # Return a fallback response
                return {
                    "mutant_id": "unknown",
                    "is_fault_adjacent": False,
                    "is_flim": True,  # Default to True when parsing fails (conservative approach)
                    "error": "Failed to parse JSON response",
                    "raw_response": llm_response,
                    "token_statistics": token_stats
                }
            
        except Exception as e:
            self.logger.error(f"Error querying LLM: {e}")
            return None

    def _extract_token_statistics(self, ollama_response: Dict, prompt: str) -> Dict:
        """
        Extract token statistics from Ollama API response
        
        Args:
            ollama_response (Dict): Raw response from Ollama API
            prompt (str): Input prompt for token counting
            
        Returns:
            Dict: Token statistics including input tokens, output tokens
        """
        try:
            # Extract token counts from Ollama response
            # Ollama API may include these fields: prompt_eval_count, eval_count
            input_tokens = ollama_response.get('prompt_eval_count', 0)
            output_tokens = ollama_response.get('eval_count', 0)
            
            # If token counts are not available from API, estimate them
            if input_tokens == 0:
                # Simple estimation: roughly 4 characters per token for English text
                input_tokens = max(1, len(prompt) // 4)
                self.logger.debug(f"Estimated input tokens: {input_tokens} (API did not provide prompt_eval_count)")
            
            if output_tokens == 0:
                response_text = ollama_response.get('response', '')
                output_tokens = max(1, len(response_text) // 4)
                self.logger.debug(f"Estimated output tokens: {output_tokens} (API did not provide eval_count)")
            
            # Extract timing information if available
            prompt_eval_duration = ollama_response.get('prompt_eval_duration', 0)  # nanoseconds
            eval_duration = ollama_response.get('eval_duration', 0)  # nanoseconds
            total_duration = ollama_response.get('total_duration', 0)  # nanoseconds
            
            # Convert nanoseconds to seconds
            prompt_eval_time_seconds = prompt_eval_duration / 1e9 if prompt_eval_duration > 0 else 0
            eval_time_seconds = eval_duration / 1e9 if eval_duration > 0 else 0
            total_time_seconds = total_duration / 1e9 if total_duration > 0 else 0
            
            token_stats = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "prompt_eval_time_seconds": round(prompt_eval_time_seconds, 4),
                "eval_time_seconds": round(eval_time_seconds, 4),
                "total_time_seconds": round(total_time_seconds, 4),
                "token_source": "api" if ollama_response.get('prompt_eval_count', 0) > 0 else "estimated"
            }
            
            self.logger.debug(f"Token statistics: {token_stats}")
            return token_stats
            
        except Exception as e:
            self.logger.warning(f"Error extracting token statistics: {e}")
            # Return default statistics
            return {
                "input_tokens": max(1, len(prompt) // 4),
                "output_tokens": max(1, len(ollama_response.get('response', '')) // 4),
                "total_tokens": 0,
                "prompt_eval_time_seconds": 0,
                "eval_time_seconds": 0,
                "total_time_seconds": 0,
                "token_source": "fallback_estimated",
                "error": str(e)
            }

    def identify_flims(self) -> Dict:
        """
        Main method to identify FLIMs in the mutant repository
        
        Returns:
            Dict: Analysis results containing FLIM identification results
        """
        try:
            self.logger.info(f"Starting FLIM identification for {self.project} {self.version}")
            
            # Check if all required resources are available
            if not self.resources_available:
                error_msg = f"跳过项目版本 {self.project} {self.version}：缺失必备资源"
                self.log_warning(error_msg)
                return {
                    "error": "Missing required resources",
                    "message": error_msg,
                    "missing_resources": self.resource_check_result["missing_resources"],
                    "resource_status": self.resource_check_result["resource_status"],
                    "skipped": True
                }
            
            # Load previous progress if available
            previous_progress = self.load_progress()
            if previous_progress:
                self.logger.info(f"Resuming from previous progress: {previous_progress.get('current_mutant_index', 0)}/{previous_progress.get('total_mutants', 0)} mutants processed")
            
            # Load original failing tests
            original_failing_tests = self.load_original_failing_tests()
            if not original_failing_tests:
                self.logger.warning("No original failing tests found")
                return {"error": "No original failing tests found"}
            
            self.logger.info(f"Loaded {len(original_failing_tests)} original failing tests")
            
            # Find all mutant files
            mutant_files = self.find_mutant_files()
            if not mutant_files:
                self.logger.warning("No mutant files found")
                return {"error": "No mutant files found"}
            
            self.logger.info(f"Found {len(mutant_files)} mutant files")
            
            # Sort mutant files by prefix, line number, and line index for better organization
            mutant_files = self.sort_mutant_files(mutant_files)
            self.logger.info("Mutant files sorted by prefix, line number, and line index")
            
            # Load model
            if not self.load_model():
                self.logger.error("Failed to load model")
                return {"error": "Failed to load model"}
            
            # Analyze each mutant
            flim_results = []
            total_mutants = len(mutant_files)
            skipped_mutants = 0
            analyzed_mutants = 0  # Track actually analyzed mutants (not attempts)
            completed_mutants = []  # Track completed mutant IDs for progress saving
            
            for i, mutant_path in enumerate(mutant_files):
                try:
                    # Generate mutant_id from path
                    mutant_id = self.get_mutant_id_from_path(mutant_path)
                    
                    self.logger.info(f"Analyzing mutant {i+1}/{total_mutants}: {mutant_id}")
                    
                    # Check if mutant file exists before processing
                    if not Path(mutant_path).exists():
                        self.logger.info(f"Skipping mutant {mutant_id}: non-existent mutant file")
                        skipped_mutants += 1
                        continue
                    
                    # Check if mutant analysis is already completed (breakpoint recovery)
                    if self.enable_resume and self.is_mutant_analysis_completed(mutant_id):
                        self.logger.info(f"Skipping mutant {mutant_id}: already completed (breakpoint recovery)")
                        skipped_mutants += 1
                        continue
                    
                    # Load mutant test results
                    mutant_failing_tests = self.get_mutant_failing_tests(mutant_id)
                    
                    # Check if mutant has test results before processing
                    if not mutant_failing_tests:
                        self.logger.info(f"Skipping mutant {mutant_id}: no test results found")
                        skipped_mutants += 1
                        continue
                    
                    # First check if this mutant should be analyzed (killed by original failing tests)
                    # Do a preliminary check without attempt number to avoid unnecessary logging
                    preliminary_result = self.analyze_mutant(mutant_path, original_failing_tests, mutant_failing_tests, attempt_number=None)
                    
                    if preliminary_result is False:
                        # Mutant was skipped (not killed by original failing tests or other issues)
                        self.logger.info(f"Skipping mutant {mutant_id}: not killed by original failing tests or analysis failed")
                        skipped_mutants += 1
                    elif preliminary_result is True:
                        # Mutant should be analyzed, now do the actual multiple attempts
                        analyzed_mutants += 1  # Count this mutant as analyzed
                        self.logger.info(f"Starting analysis for mutant {mutant_id} ({analyzed_mutants}/{total_mutants - skipped_mutants} analyzed mutants)")
                        
                        for attempt in range(1, self.identification_attempts + 1):
                            self.logger.info(f"Analyzing mutant {mutant_id} - attempt {attempt}/{self.identification_attempts}")
                            
                            # 使用带重试功能的方法
                            result = self.analyze_mutant_with_retry(mutant_path, original_failing_tests, mutant_failing_tests, attempt_number=attempt)
                            
                            if result:
                                flim_results.append(result)
                                self.logger.debug(f"Analysis completed for mutant {mutant_id} - attempt {attempt}")
                            else:
                                self.logger.warning(f"Mutant {mutant_id} - attempt {attempt} failed after all retries, skipping this attempt")
                        
                        self.logger.info(f"Completed all {self.identification_attempts} attempts for mutant {mutant_id}")
                        
                        # 汇总该变异体的分析结果
                        mutant_results = [r for r in flim_results if r.get('mutant_id') == mutant_id]
                        if mutant_results:
                            # 统计该变异体的FLIM和fault-adjacent判断结果
                            flim_judgments = [r.get('is_flim', False) for r in mutant_results]
                            fault_adjacent_judgments = [r.get('is_fault_adjacent', False) for r in mutant_results]
                            
                            flim_true_count = sum(flim_judgments)
                            fault_adjacent_true_count = sum(fault_adjacent_judgments)
                            
                            self.logger.info(f"=== 变异体 {mutant_id} 分析结果汇总 ===")
                            self.logger.info(f"总尝试次数: {len(mutant_results)}")
                            self.logger.info(f"FLIM判断: {flim_true_count}/{len(mutant_results)} 次为True")
                            self.logger.info(f"Fault-adjacent判断: {fault_adjacent_true_count}/{len(mutant_results)} 次为True")
                            
                            # 显示最终判断（基于多数投票）
                            final_flim = flim_true_count > len(mutant_results) / 2
                            final_fault_adjacent = fault_adjacent_true_count > len(mutant_results) / 2
                            
                            self.logger.info(f"最终判断 - FLIM: {final_flim}, Fault-adjacent: {final_fault_adjacent}")
                            self.logger.info(f"========================================")
                    else:
                        # Unexpected result from preliminary check
                        self.logger.warning(f"Unexpected preliminary result for mutant {mutant_id}: {preliminary_result}")
                        skipped_mutants += 1
                    
                    # Track completed mutant for progress saving
                    completed_mutants.append(mutant_id)
                    
                    # Save progress periodically (every 10 mutants) and at the end
                    if (i + 1) % 10 == 0 or (i + 1) == total_mutants:
                        self.save_progress(i + 1, total_mutants, completed_mutants, skipped_mutants)
                        
                except Exception as e:
                    self.logger.error(f"Error analyzing mutant {mutant_path}: {e}")
                    continue
            
            # Compile final results
            analysis_summary = {
                "project": self.project,
                "version": self.version,
                "total_mutants_analyzed": analyzed_mutants,
                "total_analysis_attempts": len(flim_results),
                "total_mutants_found": total_mutants,
                "total_mutants_skipped": skipped_mutants,
                "original_failing_tests_count": len(original_failing_tests),
                "analysis_timestamp": datetime.now().isoformat(),
                "flim_results": flim_results
            }
            
            # Note: FLIM identification results are stored in individual attempt results
            # Subsequent processing steps will handle the final FLIM determination
            
            self.logger.info(f"FLIM identification completed. Analyzed {analyzed_mutants} mutants with {len(flim_results)} total attempts. Skipped {skipped_mutants} mutants (missing files or test results).")
            
            return analysis_summary
            
        except Exception as e:
            self.logger.error(f"Error in FLIM identification: {e}")
            return {"error": f"FLIM identification failed: {e}"}

    def format_test_failure_info(self, test_results: Dict, dumps: bool = True, include_stack_trace: bool = True) -> Dict:
        """
        Format test failure information for LLM input
        
        Args:
            test_results (Dict): Test failure results with failing_test_name as key
            dumps (bool): Whether to format as JSON string. Defaults to True.
            include_stack_trace (bool): Whether to include stack trace information. Defaults to True.
            
        Returns:
            Dict: Formatted test failure information with test names as keys
        """
        formatted_info = {}
        for test_name, test_info in test_results.items():
            error_message = test_info.get('error_message', 'No error message')
            
            # Build the test info dictionary
            test_info_dict = {
                'error_message': error_message
            }
            
            # Only include stack_trace if include_stack_trace is True
            if include_stack_trace:
                test_info_dict['stack_trace'] = test_info.get('stack_trace', 'No stack trace')
            
            formatted_info[test_name] = test_info_dict

        # Format as JSON string if dumps is True
        if dumps:
            formatted_info = json.dumps(formatted_info, indent=2, ensure_ascii=False)
            if '\\n' in formatted_info:
                formatted_info = formatted_info.replace('\\n', '\n')
            if '\\t' in formatted_info:
                formatted_info = formatted_info.replace('\\t', '\t')
        return formatted_info

    def format_mutant_test_changes(self, test_changes: List[Dict], dumps: bool = True) -> Dict:
        """
        Format mutant test changes for LLM input, ordered by importance
        
        Args:
            test_changes (List[Dict]): Test status changes
            
        Returns:
            Dict: Formatted test change information with test names as keys, ordered by importance
        """
        # Define priority order for status changes (lower number = higher priority)
        # 按照用户期望的6级排序：
        # 1. 原本失败的现在通过了 - 最高优先级
        # 2. 原本失败但是报错信息和堆栈都变了
        # 3. 原本失败但是仅报错变了
        # 4. 原本失败但是仅堆栈变了
        # 5. 原本失败但是现在还是失败（无变化）
        # 6. 原本通过变失败 - 最低优先级
        priority_order = {
            'originally_failing_now_passing': 1,           # 原本失败现在通过
            'failing_both_error_and_stack_changed': 2,     # 报错信息和堆栈都变了
            'failing_both_error_changed_only': 3,          # 仅报错信息变了
            'failing_both_stack_changed_only': 4,          # 仅堆栈变了
            'failing_both_no_significant_change': 5,       # 失败但无显著变化
            'originally_passing_now_failing': 6            # 原本通过现在失败
        }
        
        # Collect all changes with their priorities
        changes_with_priority = []
        
        for test_name, change in test_changes.items():
            status_change = change['status_change']
            
            if status_change == 'originally_failing_now_passing':
                formatted_change = {
                    'status_change': 'failing->passing (test was fixed by mutation)'
                }
                priority = priority_order['originally_failing_now_passing']
            elif status_change == 'originally_passing_now_failing':
                formatted_change = {
                    'status_change': 'passing->failing (test was broken by mutation)'
                }
                priority = priority_order['originally_passing_now_failing']
            elif status_change == 'failing_both_error_and_stack_changed':
                error_diff = change.get('error_message_diff', 'No error diff')
                stack_diff = change.get('stack_trace_diff', 'No stack diff')
                
                formatted_change = {
                    'status_change': 'failing->failing (error message and stack trace changed)',
                    'error_diff': error_diff,
                    'stack_diff': stack_diff
                }
                priority = priority_order['failing_both_error_and_stack_changed']
            elif status_change == 'failing_both_error_changed_only':
                error_diff = change.get('error_message_diff', 'No error diff')
                
                formatted_change = {
                    'status_change': 'failing->failing (error message changed only)',
                    'error_diff': error_diff
                }
                priority = priority_order['failing_both_error_changed_only']
            elif status_change == 'failing_both_stack_changed_only':
                stack_diff = change.get('stack_trace_diff', 'No stack diff')
                
                formatted_change = {
                    'status_change': 'failing->failing (stack trace changed only)',
                    'stack_diff': stack_diff
                }
                priority = priority_order['failing_both_stack_changed_only']
            elif status_change == 'failing_both_no_significant_change':
                formatted_change = {
                    'status_change': 'failing->failing (test behavior unchanged)'
                }
                priority = priority_order['failing_both_no_significant_change']
            else:
                # 处理未知状态，给予最低优先级
                formatted_change = {
                    'status_change': f'unknown status change: {status_change}'
                }
                priority = 7  # 比所有已知状态都低
            
            changes_with_priority.append((test_name, formatted_change, priority))
        
        # Sort by priority (lower number = higher priority)
        changes_with_priority.sort(key=lambda x: x[2])
        
        # Build ordered dictionary
        formatted_changes = {}
        for test_name, formatted_change, _ in changes_with_priority:
            formatted_changes[test_name] = formatted_change
        
        # Format as JSON string if dumps is True
        if dumps:
            formatted_changes = json.dumps(formatted_changes, indent=2, ensure_ascii=False)
            if '\\n' in formatted_changes:
                formatted_changes = formatted_changes.replace('\\n', '\n')
            if '\\t' in formatted_changes:
                formatted_changes = formatted_changes.replace('\\t', '\t')
        return formatted_changes

    def is_mutant_killed_by_original_failing_tests(self, test_changes: Dict, original_failing_tests: Dict) -> bool:
        """
        Check if the mutant is killed by at least one originally failing test
        
        Args:
            test_changes (Dict): Test status changes from analyze_test_status_changes
            original_failing_tests (Dict): Original failing test information
            
        Returns:
            bool: True if mutant is killed by at least one original failing test, False otherwise
        """
        for test_name, change in test_changes.items():
            # Check if this test was originally failing
            if test_name in original_failing_tests:
                status_change = change.get('status_change', '')
                
                # Check if the test status changed from failing to passing
                # This indicates the mutant was "killed" by this originally failing test
                if status_change == 'originally_failing_now_passing':
                    return True
                    
                # Also consider cases where the test behavior changed significantly
                # (error/stack trace changes) as potential kills
                # elif 'failing_both_error_and_stack_changed' in status_change or \
                #      'failing_both_stack_changed_only' in status_change:
                #     return True
        
        return False

    def analyze_mutant_with_retry(self, mutant_path: str, original_failing_tests: Dict, mutant_failing_tests: Dict, attempt_number: int = None) -> Optional[Dict]:
        """
        带重试功能的变异体分析方法
        
        Args:
            mutant_path (str): 变异体文件路径
            original_failing_tests (Dict): 原始失败测试信息
            mutant_failing_tests (Dict): 变异体失败测试信息
            attempt_number (int, optional): 尝试次数编号
            
        Returns:
            Optional[Dict]: FLIM分析结果，如果所有重试都失败则返回None
        """
        mutant_id = self.get_mutant_id_from_path(mutant_path)
        max_retries = self.config.max_retries_per_attempt
        retry_delay = self.config.retry_delay
        backoff_factor = self.config.retry_backoff_factor
        
        for retry_count in range(max_retries + 1):  # +1 因为第一次不算重试
            try:
                if retry_count > 0:
                    # 计算当前重试的延迟时间（指数退避）
                    current_delay = retry_delay * (backoff_factor ** (retry_count - 1))
                    self.logger.info(f"  → Mutant {mutant_id} - Attempt {attempt_number} - Retry {retry_count}/{max_retries}: Waiting {current_delay:.2f}s before retry...")
                    time.sleep(current_delay)
                    self.logger.info(f"  → Mutant {mutant_id} - Attempt {attempt_number} - Retry {retry_count}/{max_retries}: Starting retry...")
                
                # 调用原始的analyze_mutant方法
                result = self.analyze_mutant(mutant_path, original_failing_tests, mutant_failing_tests, attempt_number)
                
                # 检查结果是否有效
                if result is not None:
                    if retry_count > 0:
                        self.logger.info(f"  → Mutant {mutant_id} - Attempt {attempt_number} - Retry {retry_count}/{max_retries}: Success!")
                        # 在结果中记录重试信息
                        if isinstance(result, dict):
                            result['retry_info'] = {
                                'retry_count': retry_count,
                                'max_retries': max_retries,
                                'total_attempts': retry_count + 1
                            }
                    return result
                else:
                    # 结果为None，需要重试
                    if retry_count < max_retries:
                        self.logger.warning(f"  → Mutant {mutant_id} - Attempt {attempt_number} - Retry {retry_count}/{max_retries}: Got None result, will retry...")
                    else:
                        self.logger.error(f"  → Mutant {mutant_id} - Attempt {attempt_number}: All {max_retries + 1} attempts failed (got None results)")
                        
            except requests.exceptions.Timeout as e:
                if retry_count < max_retries:
                    self.logger.warning(f"  → Mutant {mutant_id} - Attempt {attempt_number} - Retry {retry_count}/{max_retries}: Timeout error - {str(e)}, will retry...")
                else:
                    self.logger.error(f"  → Mutant {mutant_id} - Attempt {attempt_number}: All {max_retries + 1} attempts failed due to timeout")
                    
            except requests.exceptions.RequestException as e:
                if retry_count < max_retries:
                    self.logger.warning(f"  → Mutant {mutant_id} - Attempt {attempt_number} - Retry {retry_count}/{max_retries}: Request error - {str(e)}, will retry...")
                else:
                    self.logger.error(f"  → Mutant {mutant_id} - Attempt {attempt_number}: All {max_retries + 1} attempts failed due to request errors")
                    
            except json.JSONDecodeError as e:
                if retry_count < max_retries:
                    self.logger.warning(f"  → Mutant {mutant_id} - Attempt {attempt_number} - Retry {retry_count}/{max_retries}: JSON parsing error - {str(e)}, will retry...")
                else:
                    self.logger.error(f"  → Mutant {mutant_id} - Attempt {attempt_number}: All {max_retries + 1} attempts failed due to JSON parsing errors")
                    
            except Exception as e:
                if retry_count < max_retries:
                    self.logger.warning(f"  → Mutant {mutant_id} - Attempt {attempt_number} - Retry {retry_count}/{max_retries}: Unexpected error - {str(e)}, will retry...")
                else:
                    self.logger.error(f"  → Mutant {mutant_id} - Attempt {attempt_number}: All {max_retries + 1} attempts failed due to unexpected errors")
        
        # 所有重试都失败了，返回None
        return None

    def analyze_mutant(self, mutant_path: str, original_failing_tests: Dict, mutant_failing_tests: Dict, attempt_number: int = None) -> Optional[Dict]:
        """
        Analyze a single mutant for FLIM characteristics
        
        Args:
            mutant_path (str): Path to the mutant file
            original_failing_tests (Dict): Original failing test information
            mutant_failing_tests (Dict): Mutant failing test information
            attempt_number (int, optional): Specific attempt number for this identification
            
        Returns:
            Optional[Dict]: FLIM analysis result
        """
        # Record start time for this attempt
        start_time = time.time()
        
        try:
            # Generate mutant_id from path
            mutant_id = self.get_mutant_id_from_path(mutant_path)

            # Check if mutant file exists
            if not Path(mutant_path).exists():
                self.logger.info(f"Skipping mutant {mutant_id}: mutant file does not exist")
                return False if attempt_number is None else None
            
            # Check if mutant has test results
            if not mutant_failing_tests:
                self.logger.info(f"Skipping mutant {mutant_id}: no test results found")
                return False if attempt_number is None else None
            
            # Gather required information
            mutation_location = self.get_mutation_location(mutant_id)
            original_program = self.get_original_program_context(mutant_path)
            mutant_code_diff = self.get_mutant_code_diff(mutant_path)
            
            # Analyze test status changes - directly compare the two test result dictionaries
            test_changes = self.analyze_test_status_changes(original_failing_tests, mutant_failing_tests)
            
            # Check if the mutant is killed by at least one originally failing test
            # Only proceed with FLIM analysis if the mutant is killed by original failing tests
            is_killed_by_original_failing_tests = self.is_mutant_killed_by_original_failing_tests(
                test_changes, original_failing_tests
            )
            
            if not is_killed_by_original_failing_tests:
                self.logger.info(f"Skipping mutant {mutant_id}: not killed by any original failing tests")
                return False if attempt_number is None else None
            
            # Format test information
            original_failing_info = self.format_test_failure_info(original_failing_tests, dumps=True)
            mutant_test_changes_info = self.format_mutant_test_changes(test_changes, dumps=True)
            
            # Generate prompt
            prompt = self.generate_flim_prompt(
                mutant_id, str(mutation_location), original_program,
                original_failing_info, mutant_code_diff, mutant_test_changes_info
            )
            
            # 如果只是检查是否应该分析（attempt_number为None），则不进行LLM查询和保存
            if attempt_number is None:
                return True  # 表示这个变异体应该被分析
            
            # Record time before LLM query
            llm_start_time = time.time()
            
            # Query LLM
            result = self.query_llm(prompt)
            
            # Calculate time costs
            llm_end_time = time.time()
            total_end_time = time.time()
            
            llm_time_cost = llm_end_time - llm_start_time
            total_time_cost = total_end_time - start_time
            preprocessing_time_cost = llm_start_time - start_time
            
            if result:
                result['mutant_id'] = mutant_id
                result['mutant_path'] = mutant_path
                result['analysis_timestamp'] = datetime.now().isoformat()
                # 保存排序后的test_changes而不是原始的test_changes
                result['test_changes'] = self.format_mutant_test_changes(test_changes, dumps=False)
                result['attempt_number'] = attempt_number  # 记录识别次数
                
                # Add time cost statistics
                result['time_cost'] = {
                    'total_time_seconds': round(total_time_cost, 4),
                    'preprocessing_time_seconds': round(preprocessing_time_cost, 4),
                    'llm_query_time_seconds': round(llm_time_cost, 4),
                    'start_timestamp': start_time,
                    'end_timestamp': total_end_time
                }
                
                # Add token statistics and calculate token output speed
                token_stats = result.get('token_statistics', {})
                if token_stats:
                    # Calculate token output speed (tokens per second)
                    output_tokens = token_stats.get('output_tokens', 0)
                    if output_tokens > 0 and llm_time_cost > 0:
                        token_output_speed = round(output_tokens / llm_time_cost, 2)
                    else:
                        token_output_speed = 0.0
                    
                    # Add token output speed to token statistics
                    token_stats['token_output_speed_tokens_per_second'] = token_output_speed
                    
                    # Update the result with enhanced token statistics
                    result['token_statistics'] = token_stats
                
                # Log detailed identification results for this attempt
                is_flim = result.get('is_flim', False)
                is_fault_adjacent = result.get('is_fault_adjacent', False)
                reasoning = result.get('reasoning', 'N/A')
                time_cost = result.get('time_cost', {})
                
                self.logger.info(f"  → Mutant {mutant_id} - Attempt {attempt_number} Results:")
                self.logger.info(f"    • FLIM: {is_flim}")
                self.logger.info(f"    • Fault-Adjacent: {is_fault_adjacent}")
                self.logger.info(f"    • Time Cost: {time_cost.get('total_time_seconds', 0):.4f}s (Preprocessing: {time_cost.get('preprocessing_time_seconds', 0):.4f}s, LLM: {time_cost.get('llm_query_time_seconds', 0):.4f}s)")
                if reasoning != 'N/A' and len(str(reasoning)) < 200:  # Only log short reasoning
                    self.logger.info(f"    • Reasoning: {reasoning}")
                
                # Save individual mutant result
                self.save_mutant_result(mutant_id, result, attempt_number)
                
            else:
                # Even if analysis failed, create a result with time cost information
                failed_result = {
                    'mutant_id': mutant_id,
                    'mutant_path': mutant_path,
                    'analysis_timestamp': datetime.now().isoformat(),
                    'attempt_number': attempt_number,
                    'analysis_status': 'failed',
                    'error_message': 'No result from LLM',
                    'time_cost': {
                        'total_time_seconds': round(total_time_cost, 4),
                        'preprocessing_time_seconds': round(preprocessing_time_cost, 4),
                        'llm_query_time_seconds': round(llm_time_cost, 4),
                        'start_timestamp': start_time,
                        'end_timestamp': total_end_time
                    }
                }
                
                self.logger.warning(f"  → Mutant {mutant_id} - Attempt {attempt_number}: Analysis failed (no result from LLM)")
                self.logger.info(f"    • Time Cost: {total_time_cost:.4f}s (Preprocessing: {preprocessing_time_cost:.4f}s, LLM: {llm_time_cost:.4f}s)")
                
                # Save the failed result with time cost information
                self.save_mutant_result(mutant_id, failed_result, attempt_number)
                
            return result
            
        except Exception as e:
            # Calculate time cost even in case of exception
            error_end_time = time.time()
            error_total_time = error_end_time - start_time
            
            # Create error result with time cost information if attempt_number is provided
            if attempt_number is not None:
                error_result = {
                    'mutant_id': self.get_mutant_id_from_path(mutant_path),
                    'mutant_path': mutant_path,
                    'analysis_timestamp': datetime.now().isoformat(),
                    'attempt_number': attempt_number,
                    'analysis_status': 'error',
                    'error_message': str(e),
                    'time_cost': {
                        'total_time_seconds': round(error_total_time, 4),
                        'preprocessing_time_seconds': round(error_total_time, 4),  # All time considered as preprocessing since LLM wasn't reached
                        'llm_query_time_seconds': 0.0,
                        'start_timestamp': start_time,
                        'end_timestamp': error_end_time
                    }
                }
                
                try:
                    self.save_mutant_result(error_result['mutant_id'], error_result, attempt_number)
                except:
                    pass  # Don't let save errors prevent error logging
            
            self.logger.error(f"Error analyzing mutant {mutant_path}: {e}")
            if attempt_number is not None:
                self.logger.info(f"    • Time Cost (before error): {error_total_time:.4f}s")
            return None
    
    def save_results(self, results: Dict):
        """
        Save FLIM identification results to files
        
        Args:
            results (Dict): FLIM identification results
        """
        try:
            # Save complete results
            results_file = self.output_path / "flim_results.json"
            with open(results_file, 'w') as f:
                json.dump(results, f, indent=2)
            
            # Save filtered mutant lists
            non_flim_file = self.output_path / "non_flim_mutants.json"
            with open(non_flim_file, 'w') as f:
                json.dump(results['non_flim_mutants'], f, indent=2)
            
            # Save fault-adjacent mutants list
            fault_adjacent_file = self.output_path / "fault_adjacent_mutants.json"
            with open(fault_adjacent_file, 'w') as f:
                json.dump(results['fault_adjacent_mutants'], f, indent=2)
            
            # Save non-fault-adjacent mutants list (these are FLIMs)
            non_fault_adjacent_file = self.output_path / "non_fault_adjacent_mutants.json"
            with open(non_fault_adjacent_file, 'w') as f:
                json.dump(results['non_fault_adjacent_mutants'], f, indent=2)
            
            # Generate and save analysis report
            self.generate_analysis_report(results)
            
            self.logger.info(f"Results saved to {self.output_path}")
            self.logger.info(f"Individual mutant results saved to {self.mutant_results_path}")
            
        except Exception as e:
            self.logger.error(f"Error saving results: {e}")
    
    def generate_analysis_report(self, results: Dict):
        """
        Generate a human-readable analysis report
        
        Args:
            results (Dict): FLIM identification results
        """
        report_file = self.output_path / "flim_analysis_report.txt"
        
        try:
            with open(report_file, 'w') as f:
                f.write("FLIM (Fault Localization Interference Mutant) Analysis Report\n")
                f.write("=" * 60 + "\n\n")
                
                f.write(f"Project: {results['project']}\n")
                f.write(f"Version: {results['version']}\n")
                f.write(f"Analysis Date: {results['analysis_timestamp']}\n\n")
                
                f.write("Summary Statistics:\n")
                f.write("-" * 20 + "\n")
                f.write(f"Total Mutants Found: {results.get('total_mutants_found', 0)}\n")
                f.write(f"Total Mutants Skipped: {results.get('total_mutants_skipped', 0)}\n")
                f.write(f"Total Mutants Analyzed: {results['total_mutants_analyzed']}\n")
                f.write(f"FLIMs Identified: {results.get('flim_count', 0)}\n")
                f.write(f"Non-FLIMs: {len(results.get('non_flim_mutants', []))}\n")
                f.write(f"Fault-Adjacent Mutants: {results.get('fault_adjacent_count', 0)}\n")
                f.write(f"Non-Fault-Adjacent Mutants: {len(results.get('non_fault_adjacent_mutants', []))}\n")
                if results['total_mutants_analyzed'] > 0:
                    f.write(f"FLIM Ratio: {results.get('flim_count', 0) / results['total_mutants_analyzed'] * 100:.2f}%\n")
                    f.write(f"Fault-Adjacent Ratio: {results.get('fault_adjacent_count', 0) / results['total_mutants_analyzed'] * 100:.2f}%\n")
                else:
                    f.write("FLIM Ratio: N/A (no mutants analyzed)\n")
                    f.write("Fault-Adjacent Ratio: N/A (no mutants analyzed)\n")
                f.write("\n")
                
                if results['flim_mutants']:
                    f.write("Identified FLIMs:\n")
                    f.write("-" * 15 + "\n")
                    for mutant_id in results['flim_mutants']:
                        detail = results['detailed_results'].get(mutant_id, {})
                        reasoning = detail.get('reasoning', 'No reasoning provided')
                        f.write(f"- {mutant_id}\n")
                        f.write(f"  Reasoning: {reasoning}\n\n")
                
                f.write("Output Files:\n")
                f.write("-" * 12 + "\n")
                f.write("- flim_results.json: Complete analysis results\n")
                f.write("- non_flim_mutants.json: List of non-FLIM mutants\n")
                f.write("- fault_adjacent_mutants.json: List of fault-adjacent mutants\n")
                f.write("- non_fault_adjacent_mutants.json: List of non-fault-adjacent mutants (FLIMs)\n")
                f.write("- mutant_results/: Individual mutant analysis results by mutant_id\n")
                f.write("  Each mutant folder contains model-specific result files\n\n")
                
                f.write("Recommendation:\n")
                f.write("-" * 14 + "\n")
                f.write("Consider excluding identified FLIMs from fault localization analysis\n")
                f.write("to improve the effectiveness of MBFL techniques.\n")
                
        except Exception as e:
            self.logger.error(f"Error generating analysis report: {e}")


class FLIMBatchProcessor:
    """
    FLIM批量处理器,支持批量执行FLIM识别任务
    """
    
    def __init__(self, config: Optional[FLIMConfig] = None):
        """
        初始化批量处理器
        
        Args:
            config (FLIMConfig, optional): FLIM配置对象,如果为None则使用默认配置
        """
        self.config = config or FLIMConfig()
        self.logger = self._setup_batch_logging()
        
        # 初始化多级日志记录器引用
        self.batch_logger = self.logger
        self.project_loggers = {}  # 存储项目级logger的字典
    
    def _setup_batch_logging(self):
        """设置批量处理日志，基于输出路径的分层日志记录"""
        # 获取批处理级日志目录（输出结果保存路径的上一级目录）
        _, _, _, output_path_base, _ = self.config.get_mutation_test_paths("Chart")  # 使用任意项目获取基础路径
        batch_log_dir = output_path_base.parent / "logs"
        batch_log_dir.mkdir(parents=True, exist_ok=True)
        
        # 批处理级日志文件
        batch_log_file = batch_log_dir / f"flim_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        # 创建独立的批处理logger
        batch_logger = logging.getLogger("flim.batch")
        batch_logger.handlers.clear()
        batch_logger.setLevel(logging.INFO)
        
        # 创建formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        # 批处理级文件handler
        batch_handler = logging.FileHandler(batch_log_file)
        batch_handler.setFormatter(formatter)
        batch_handler.setLevel(logging.INFO)
        batch_logger.addHandler(batch_handler)
        
        # 控制台handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)
        batch_logger.addHandler(console_handler)
        
        # 防止日志向上传播
        batch_logger.propagate = False
        
        return batch_logger
    
    def _setup_project_logging(self, project: str):
        """设置项目级日志记录"""
        # 获取项目级日志目录（输出结果保存的项目路径下）
        _, _, _, output_path_base, _ = self.config.get_mutation_test_paths(project)
        project_log_dir = output_path_base / project
        project_log_dir.mkdir(parents=True, exist_ok=True)
        
        # 项目级日志文件
        project_log_file = project_log_dir / f"flim_project_{project}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        # 创建独立的项目logger
        project_logger_name = f"flim.project.{project}"
        project_logger = logging.getLogger(project_logger_name)
        project_logger.handlers.clear()
        project_logger.setLevel(logging.INFO)
        
        # 创建formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        # 项目级文件handler
        project_handler = logging.FileHandler(project_log_file)
        project_handler.setFormatter(formatter)
        project_handler.setLevel(logging.INFO)
        project_logger.addHandler(project_handler)
        
        # 防止日志向上传播
        project_logger.propagate = False
        
        # 将项目logger存储到字典中
        self.project_loggers[project] = project_logger
        
        return project_logger
    
    def log_warning(self, message: str, project: str = None):
        """
        记录warning信息到所有相关级别的日志中
        
        Args:
            message: 警告信息
            project: 项目名称，如果提供则也记录到项目级日志
        """
        # 记录到批处理级日志
        self.batch_logger.warning(message)
        
        # 如果提供了项目名称且项目logger存在，也记录到项目级日志
        if project and project in self.project_loggers:
            self.project_loggers[project].warning(message)
    
    def log_error(self, message: str, project: str = None):
        """
        记录error信息到所有相关级别的日志中
        
        Args:
            message: 错误信息
            project: 项目名称，如果提供则也记录到项目级日志
        """
        # 记录到批处理级日志
        self.batch_logger.error(message)
        
        # 如果提供了项目名称且项目logger存在，也记录到项目级日志
        if project and project in self.project_loggers:
            self.project_loggers[project].error(message)
    
    def process_single_project_version(self, project: str, version: str) -> Dict:
        """
        处理单个项目版本
        """
        try:
            self.logger.info(f"开始处理 {project} 版本 {version}")

            # 创建FLIM识别器
            flim_identifier = FLIMIdentifier(
                project, version, self.config,
                batch_mode=True, batch_processor=self
            )

            # 执行FLIM识别
            results = flim_identifier.identify_flims()

            # ---------- 1) results 为空 ----------
            if not results:
                msg = f"{project} 版本 {version} 失败：identify_flims 返回空结果"
                self.log_error(msg, project)
                return {
                    'project': project,
                    'version': version,
                    'status': 'failed',
                    'error': 'identify_flims returned empty'
                }

            # ---------- 2) 缺资源导致跳过 ----------
            if results.get('skipped', False):
                msg = results.get('message', '缺失必备资源')
                self.log_warning(f"跳过 {project} 版本 {version}：{msg}", project)
                return {
                    'project': project,
                    'version': version,
                    'status': 'skipped',
                    'reason': 'missing_resources',
                    'message': msg,
                    'missing_resources': results.get('missing_resources', []),
                    'resource_status': results.get('resource_status', {})
                }

            # ---------- 3) identify_flims 明确返回 error ----------
            if 'error' in results:
                err = results.get('error', 'unknown error')
                self.log_error(f"处理 {project} 版本 {version} 失败：{err}", project)
                return {
                    'project': project,
                    'version': version,
                    'status': 'failed',
                    'error': err,
                    'message': results.get('message', '')
                }

            # ---------- 4) 真成功：再读 total_mutants_analyzed ----------
            total = results.get('total_mutants_analyzed', None)
            if total is None:
                # 兜底：避免再次 KeyError，同时把返回结构打印出来方便排查
                keys = list(results.keys())
                self.log_error(
                    f"处理 {project} 版本 {version} 返回结构异常：缺少 total_mutants_analyzed，keys={keys}",
                    project
                )
                return {
                    'project': project,
                    'version': version,
                    'status': 'failed',
                    'error': 'missing total_mutants_analyzed in results',
                    'keys': keys
                }

            self.logger.info(f"成功完成 {project} 版本 {version} 的FLIM识别")
            self.logger.info(f"分析完成: 共分析了 {total} 个变异体")

            return {
                'project': project,
                'version': version,
                'status': 'success',
                'total_mutants': total,
                'output_path': str(flim_identifier.output_path)
            }

        except Exception as e:
            self.logger.error(f"处理 {project} 版本 {version} 时发生异常: {e}")
            return {
                'project': project,
                'version': version,
                'status': 'error',
                'error': str(e)
            }
    
    def process_project_all_versions(self, project: str) -> List[Dict]:
        """
        处理项目的所有版本
        
        Args:
            project (str): 项目名称
            
        Returns:
            List[Dict]: 所有版本的处理结果
        """
        try:
            # 设置项目级日志记录
            project_logger = self._setup_project_logging(project)
            
            versions = get_versions(project)
            results = []
            
            self.logger.info(f"开始处理项目 {project},共 {len(versions)} 个版本")
            project_logger.info(f"开始处理项目 {project},共 {len(versions)} 个版本")
            
            for version in versions:
                project_logger.info(f"开始处理版本 {version}")
                result = self.process_single_project_version(project, str(version))
                results.append(result)
                
                if result['status'] == 'success':
                    project_logger.info(f"版本 {version} 处理成功，分析了 {result.get('total_mutants', 0)} 个变异体")
                else:
                    project_logger.error(f"版本 {version} 处理失败: {result.get('error', 'Unknown error')}")
            
            # 项目级汇总
            successful_versions = sum(1 for r in results if r['status'] == 'success')
            total_mutants = sum(r.get('total_mutants', 0) for r in results if r['status'] == 'success')
            project_logger.info(f"项目 {project} 处理完成: {successful_versions}/{len(versions)} 个版本成功，共分析 {total_mutants} 个变异体")
            
            return results
            
        except Exception as e:
            self.logger.error(f"获取项目 {project} 的版本信息失败: {e}")
            return [{
                'project': project,
                'version': 'unknown',
                'status': 'error',
                'error': f"Failed to get versions: {e}"
            }]
    
    def process_all_projects(self, projects: Optional[List[str]] = None) -> Dict:
        """
        处理所有项目
        
        Args:
            projects (List[str], optional): 要处理的项目列表,如果为None则使用配置中的所有支持项目
            
        Returns:
            Dict: 所有项目的处理结果汇总
        """
        if projects is None:
            projects = self.config.SUPPORTED_PROJECTS
        
        all_results = []
        summary = {
            'total_projects': len(projects),
            'successful_projects': 0,
            'failed_projects': 0,
            'total_versions_processed': 0,
            'successful_versions': 0,
            'failed_versions': 0,
            'start_time': datetime.now().isoformat(),
            'end_time': None,
            'results': []
        }
        
        self.logger.info(f"开始批量处理,共 {len(projects)} 个项目")
        
        for project in projects:
            self.logger.info(f"处理项目: {project}")
            project_results = self.process_project_all_versions(project)
            
            # 统计项目级别的结果
            project_success = any(r['status'] == 'success' for r in project_results)
            if project_success:
                summary['successful_projects'] += 1
            else:
                summary['failed_projects'] += 1
            
            # 统计版本级别的结果
            for result in project_results:
                summary['total_versions_processed'] += 1
                if result['status'] == 'success':
                    summary['successful_versions'] += 1
                else:
                    summary['failed_versions'] += 1
            
            all_results.extend(project_results)
        
        summary['end_time'] = datetime.now().isoformat()
        summary['results'] = all_results
        
        # 保存汇总结果
        self._save_batch_summary(summary)
        
        self.logger.info("批量处理完成")
        self.logger.info(f"成功处理项目: {summary['successful_projects']}/{summary['total_projects']}")
        self.logger.info(f"成功处理版本: {summary['successful_versions']}/{summary['total_versions_processed']}")
        
        return summary
    
    def _save_batch_summary(self, summary: Dict):
        """保存批量处理汇总结果"""
        try:
            output_dir = Path("batch_results")
            output_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            summary_file = output_dir / f"flim_batch_summary_{timestamp}.json"
            
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"批量处理汇总结果已保存到: {summary_file}")
            
        except Exception as e:
            self.logger.error(f"保存批量处理汇总结果失败: {e}")


def main():
    """主函数,所有参数已硬编码"""
    # breakpoint()
  
    # ==================== 硬编码配置参数 ====================
    # 运行模式选项: 'single'(单个版本), 'project'(项目所有版本), 'batch'(所有项目)
    mode = 'single'
    
    # 单个项目版本处理参数
    project = 'Chart'  # 可选项: Chart, Closure, Lang, Math, Mockito, Time 等
                     
    version = '9'      # 项目版本号,如: 1, 2, 3, 4, 5 等
    
    # 批量处理项目列表 (当mode='batch'时使用)
    projects = [  "Collections", "JacksonDatabind", "JxPath", "Jsoup", "Compress"]
    # projects = None  # None表示处理所有项目
    
    # 数据集配置参数
    config_dataset = 'Defects4J'          # 可选项: 'Defects4J' 或 None(使用默认值)
    config_dataset_version = 'D4JCleanCD4J'  # 可选项: 'D4JCleanCD4J', 'D4JCleanCD4J_v2' 或 None(使用默认值)
    config_mutation_type = 'NeuralMutation'    # 可选项: 'TraditionalMutation', 'NeuralMutation' 或 None(使用默认值)
    config_mutation_tool = 'mBERT'    # 可选项: 'major', 'mBERT' 或 None(使用默认值)
    
    # ==================== 执行逻辑 ====================
    
    # 创建配置
    config = FLIMConfig(
        dataset=config_dataset,
        dataset_version=config_dataset_version,
        mutation_type=config_mutation_type,
        mutation_tool=config_mutation_tool
    )
    
    if mode == 'single':
        if not project or not version:
            print("单个版本模式需要指定 project 和 version 参数")
            sys.exit(1)
        
        # 单个项目版本处理
        flim_identifier = FLIMIdentifier(project, version, config)
        results = flim_identifier.identify_flims()
        
        if results and 'error' not in results:
            print(f"FLIM识别完成: {project} 版本 {version}")
            print(f"结果保存到: {flim_identifier.output_path}")
            print(f"分析完成: 共分析了 {results['total_mutants_analyzed']} 个变异体")
        else:
            error_msg = results.get('error', '未知错误') if results else '识别过程失败'
            print(f"FLIM识别失败: {project} 版本 {version} - {error_msg}")
            sys.exit(1)
    
    elif mode == 'project':
        if not project:
            print("项目模式需要指定 project 参数")
            sys.exit(1)
        
        # 单个项目所有版本处理
        batch_processor = FLIMBatchProcessor(config)
        results = batch_processor.process_project_all_versions(project)
        
        successful = sum(1 for r in results if r['status'] == 'success')
        print(f"项目 {project} 处理完成: {successful}/{len(results)} 个版本成功")
    
    elif mode == 'batch':
        # 批量处理
        batch_processor = FLIMBatchProcessor(config)
        summary = batch_processor.process_all_projects(projects)
        
        print(f"批量处理完成:")
        print(f"  成功处理项目: {summary['successful_projects']}/{summary['total_projects']}")
        print(f"  成功处理版本: {summary['successful_versions']}/{summary['total_versions_processed']}")



if __name__ == "__main__":
    main()