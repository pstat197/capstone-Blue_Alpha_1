# Marketing Mix Modeling – Prior Sensitivity Analysis
**BlueAlpha Capstone Project 1**

A Bayesian prior sensitivity analysis framework for Marketing Mix Models (MMM).  
This project systematically perturbs prior specifications and measures how sensitive key MMM outputs—such as ROI estimates and channel contributions—are to prior assumptions. The goal is to help analysts and stakeholders understand which conclusions are robust and which depend heavily on modeling choices.

---

## Project Goal
This project builds a reusable tool to analyze how sensitive Bayesian Marketing Mix Model (MMM) results are to prior assumptions, using **Google Meridian** as the underlying modeling framework.

## Motivation
MMM is widely used to attribute revenue to marketing channels, but its conclusions depend on prior beliefs about parameters such as channel ROI and ad effectiveness.  
This project quantifies how changes in these priors affect key model outputs, helping teams assess robustness and identify assumptions that most influence results.

## Current Scope (Base Deliverable)
- Vary one prior at a time
- Re-run Meridian for each prior setting
- Compare ROI estimates to a baseline configuration
- Visualize sensitivity through plots and summary tables

## Dataset
- `monthly_mocha.csv`: example monthly marketing dataset used for development and testing

## Repository Structure
- `src/`: core Python logic for running models and sensitivity analysis
- `notebooks/`: exploratory and development notebooks
- `outputs/`: generated plots and result tables
- `configs/`: Meridian configuration files

## Next Steps
- Get a single baseline Meridian run working end-to-end
- Implement automated prior perturbation loops
- Extract and store ROI metrics for comparison

## Setup (VSCode + venv)

### Windows
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```
### MacOS/Linux

```powershell
python3 -m venv .venv 
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```
## Contributors
BlueAlpha Capstone Project 1 Group

- **Jasper Luo** (@JasperLuo0228)
- **Jimmy Wu** (@JimmyWu-312)
- **Coraline Zhu** (@DaixiZhu)
- **Aidan Frazier** (@aidansfrazier)
- **Quinlan Wilson** (@Quinland03)
