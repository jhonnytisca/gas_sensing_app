import os
import shutil
import yaml
from pathlib import Path

from PyQt6.QtWidgets import QFileDialog

from gas_sensing_app.core.worker import ExperimentWorker
from gas_sensing_app.gui.styles.theme_manager import (load_theme,
                                        update_plot_theme)


ASSETS_DIR = Path(__file__).parent.parent / "assets"

class DashboardController:
    
    def __init__(self,window):
        self.window = window
        
        # Apply configurations
        self.config_path = "config.yaml" 
        self.recipe_path = None
        self._create_dummy_files()
        
        # connect associations
        self.window.theme_selector.currentIndexChanged.connect(
            self.change_theme
        )
        self.window.load_recipe_btn.clicked.connect(self.select_recipe)
        self.window.start_recipe_btn.clicked.connect(self.start_recipe_mode)
        self.window.start_manual_btn.clicked.connect(self.start_manual_mode)
        self.window.apply_manual_btn.clicked.connect(self.apply_manual_changes)
        self.window.stop_btn.clicked.connect(self.stop_experiment)
        
        
    # connect functions
    def change_theme(self,index):
        theme = self.window.theme_selector.itemData(index)
        self.window.setStyleSheet(
            load_theme(theme)
        )
        update_plot_theme(self.window.mfc_plot, theme)
        update_plot_theme(self.window.res_plot, theme)
    
    def refresh_style(self,widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        
    def start_recipe_mode(self):
        self.prepare_data_arrays()
        self.worker = ExperimentWorker(self.config_path, self.recipe_path, mode='recipe')
        self.connect_and_start_worker()
        self.window.control_tabs.setTabEnabled(1, False) 
        self.window.start_recipe_btn.setEnabled(False)
        self.window.load_recipe_btn.setEnabled(False)
    
    def select_recipe(self):
        file, _ = QFileDialog.getOpenFileName(self.window, "Select YAML Recipe", "", "YAML Files (*.yaml)")
        if file:
            self.recipe_path = file
            self.window.status_label.setText(f"Loaded: {os.path.basename(file)}")
            self.window.status_label.setProperty("textColor", "success")
            self.window.status_label.setProperty("fontWeight", "bold")
            self.refresh_style(self.window.status_label)
            self.window.start_recipe_btn.setEnabled(True)
    
    def start_manual_mode(self):
        self.prepare_data_arrays()
        self.worker = ExperimentWorker(self.config_path, mode='manual')
        self.connect_and_start_worker()
        self.window.control_tabs.setTabEnabled(0, False) 
        self.window.start_manual_btn.setEnabled(False)
        self.window.apply_manual_btn.setEnabled(True)
        self.apply_manual_changes()
        
    def apply_manual_changes(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            flow_targets = {
                1: self.window.mfc1_val.value(), 2: self.window.mfc2_val.value(),
                3: self.window.mfc3_val.value(), 4: self.window.mfc4_val.value()
            }
            # CHANGED: Extracts the manual targets directly as a clean boolean state flag
            shutter_open_target = self.window.shutter_checkbox.isChecked()
            self.worker.update_manual_setpoints(shutter_open_target, flow_targets)
            print(f"[Manual Mode Update]: Staging Shutter_Open={shutter_open_target}, Flows={list(flow_targets.values())}")
    
    def stop_experiment(self):
        if hasattr(self, 'worker') and self.worker.isRunning(): self.worker.is_running = False
            

    def connect_and_start_worker(self):
        self.worker.data_sig.connect(self.update_live_data)
        self.worker.status_sig.connect(self.update_status)
        self.worker.error_sig.connect(self.handle_worker_error)
        self.worker.finished_sig.connect(self.on_experiment_finished)
        self.window.stop_btn.setEnabled(True)
        self.worker.start()

    def prepare_data_arrays(self):
        self.data_history = {"time": [], "resistance": [], "flows": [[], [], [], []], "shutter": []}
        self.window.res_curve.setData([], [])
        self.window.shutter_curve.setData([], [])
        for curve in self.window.mfc_curves: curve.setData([], [])
    
    
    def update_live_data(self, data):
        self.window.res_display.setText(f"{data['resistance']:.4e} Ω")
        elapsed_t = len(self.data_history['time'])
        self.data_history['time'].append(elapsed_t)
        
        self.data_history['resistance'].append(data['resistance'])
        self.window.res_curve.setData(self.data_history['time'], self.data_history['resistance'])
        
        self.data_history['shutter'].append(data['shutter'])
        self.window.shutter_curve.setData(self.data_history['time'], self.data_history['shutter'])
        
        for i in range(4):
            self.data_history['flows'][i].append(data['flows'][i])
            self.window.mfc_curves[i].setData(self.data_history['time'], self.data_history['flows'][i])

    def update_status(self, text): 
        self.window.status_label.setText(text)
        
    def handle_worker_error(self, err):
        print(f"[CRITICAL WARNING]: {err}"); self.stop_experiment()
    

    def on_experiment_finished(self, log_path):
        self.window.stop_btn.setEnabled(False)
        self.window.apply_manual_btn.setEnabled(False)
        self.window.control_tabs.setTabEnabled(0, True)
        self.window.control_tabs.setTabEnabled(1, True)
        self.window.start_manual_btn.setEnabled(True)
        if self.recipe_path: self.window.start_recipe_btn.setEnabled(True)
        self.window.load_recipe_btn.setEnabled(True)
        print(f"Hardware loop cleanly halted. Session log saved to: {log_path}")
        
    
    def _create_dummy_files(self):
        """
        Ensures the local lab computer runtime workspace folders and files exist.
        Copies raw templates from the assets folder to preserve structural comments.
        """
        # Define template files paths
        template_config = ASSETS_DIR / "config.template.yaml"
        template_recipe = ASSETS_DIR / "recipe.template.yaml"
        
        # 1. Check and copy live config.yaml fallback
        if not os.path.exists(self.config_path):
            if template_config.exists():
                shutil.copy(template_config, self.config_path)
                print("[System Info] Generated local 'config.yaml' from master assets template.")
            else:
                # Critical safety net fallback if assets folder is completely missing
                print("[Critical Warning] 'assets/config.template.yaml' not found! Falling back to safe hardcoded defaults.")
                fallback_config = {
                    'hardware': {
                        'use_mock': True,
                        'keithley_2400': {'port': 'MOCK_PORT', 'auto_range': False, 'manual_range': 200000, 'four_wire': True},
                        'shutter': {'port': 'MOCK_SHUTTER', 'baud_rate': 115200, 'open_angle': 90, 'closed_angle': 0},
                        'mfc_controller': {'port': 'MOCK_MFC', 'range_sccm': {1: 1000, 2: 1000, 3: 200, 4: 200}}
                    },
                    'logging': {
                        'data_log': {'folder': 'data', 'filename_prefix': 'sensing_run'},
                        'console_log': {'enabled': True, 'folder': 'logs', 'filename_prefix': 'log'}
                    }
                }
                with open(self.config_path, 'w') as f:
                    yaml.dump(fallback_config, f)

        # 2. Extract operational workspace directories dynamically from config.yaml
        try:
            with open(self.config_path, 'r') as f:
                cfg = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[Error] Failed to read config.yaml layout: {e}")
            cfg = {}

        # Safely fall back to default string folders if parameters are missing inside config.yaml
        data_dir = cfg.get('logging', {}).get('data_log', {}).get('folder', 'data')
        log_dir = cfg.get('logging', {}).get('console_log', {}).get('folder', 'logs')
        recipe_dir = "recipes"

        # 3. Create all dynamic storage directories safely (skips if they already exist)
        for folder in [data_dir, log_dir, recipe_dir]:
            Path(folder).mkdir(parents=True, exist_ok=True)

        # 4. Seed the user recipes workspace folder with a base profile if it is empty
        self.recipe_path = os.path.join(recipe_dir, "dummy_recipe.yaml")
        if not os.path.exists(self.recipe_path):
            if template_recipe.exists():
                shutil.copy(template_recipe, self.recipe_path)
                print(f"[System Info] Seeded recipes workspace with: {os.path.basename(self.recipe_path)}")
            else:
                # Quick programmatic fallback array if the assets/ recipe template is missing
                fallback_recipe = {
                    'steps': [
                        {'name': 'Purge_Phase', 'duration': 10, 'shutter_open': False, 'mfc_flows': {1: 120, 2: 10}},
                        {'name': 'Expose_Gas', 'duration': 20, 'shutter_open': True, 'mfc_flows': {1: 100, 2: 30}},
                        {'name': 'Recovery_Phase', 'duration': 15, 'shutter_open': False, 'mfc_flows': {1: 120, 2: 10}}
                    ]
                }
                with open(self.recipe_path, 'w') as f:
                    yaml.dump(fallback_recipe, f)
      