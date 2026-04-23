# MBFL-FLIM

## Overview

This repository contains the implementation and experimental results for Mutation-Based Fault Localization (MBFL), with a focus on analyzing Fault Localization Interference Mutants (FLIMs).

FLIMs are a class of mutants that may negatively affect fault localization effectiveness. This project includes scripts for FLIM identification, fault localization evaluation, and visualization under different mutation strategies (e.g., Major and μBERT).

---

## Project Structure

```text
MBFL-FLIM/
├── flim_detection/
├── fault_localization/
├── plotting/
├── results/
├── README.md
```

---

## Directory Description

### 1. `flim_detection/`

This folder contains scripts for identifying and analyzing FLIMs.

Typical functionalities include:

* Processing mutation results
* Identifying interference mutants (FLIMs)
* Generating intermediate analysis data

---

### 2. `fault_localization/`

This folder contains the implementation of fault localization techniques.

It mainly includes:

* Calculation of suspiciousness metrics (e.g., MBFL metrics)
* Integration of mutation results into fault localization
* Evaluation of localization performance (e.g., EXAM score)

---

### 3. `plotting/`

This folder contains scripts for generating figures used in the experiments.

Typical outputs include:

* Comparison plots between different mutation strategies
* Visualization of EXAM score distributions
* Statistical summaries of experimental results

---

### 4. `results/`

This folder stores selected experimental results.

The results are typically organized by mutation strategy, such as:

* `major/` : results based on traditional mutation (Major)
* `mBERT/` : results based on neural mutation (μBERT)

Due to size limitations, only representative results are included.

---

## Usage

Scripts can be executed directly. For example:

```bash
python flim_detection/build_new_excel.py
python fault_localization/StatementSus_calculator_fxj.py
python plotting/draw_remove_oracle_flims.py
```

---

## Notes

* This repository provides the core implementation used in the experiments.
* Some scripts depend on specific environments and external datasets, and may require additional configuration.
* Full datasets and intermediate files are not included due to size constraints.

---

## Additional Information

* Dataset: Defects4J benchmark
* Mutation tools: Major and μBERT

This repository is intended for research reference.
