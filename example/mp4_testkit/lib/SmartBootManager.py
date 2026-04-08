"""
智能啟動系統 - 根據運行狀態決定是否啟動 WiFi
"""

from lib.ConfigManager import ConfigManager
from lib.WiFiManager import WiFiManager
import time

class SmartBootManager:
    """
    智能啟動管理器
    
    邏輯:
    1. 檢查 loop_one_success 狀態
    2. False → 啟動 WiFi + WebREPL (1分鐘等待)
    3. True → 跳過 WiFi,直接進入主程式
    4. 進入主程式前設置 loop_one_success = False
    5. 完成一個 loop 後設置 loop_one_success = True
    """
    
    def __init__(self):
        """初始化啟動管理器"""
        self.cfg = ConfigManager()
        self.wifi = None
        self.webrepl_timeout = 60  # WebREPL 等待時間(秒)
    
    def check_and_boot(self):
        """
        檢查狀態並決定啟動流程
        
        Returns:
            bool: 是否啟動了 WiFi
        """
        print("\n" + "="*70)
        print("🚀 智能啟動系統")
        print("="*70)
        
        # 獲取上次 loop 狀態
        loop_one_success = self.cfg.get_state('loop_one_success', default=False)
        boot_count = self.cfg.get_state('boot_count', default=0)
        last_error = self.cfg.get_state('last_error', default='none')
        
        print(f"\n📊 系統狀態:")
        print(f"  啟動次數: {boot_count}")
        print(f"  上次循環: {'✓ 成功' if loop_one_success else '✗ 失敗'}")
        print(f"  上次錯誤: {last_error}")
        
        # 決定是否啟動 WiFi
        if loop_one_success:
            print(f"\n✓ 上次運行正常,跳過 WiFi 啟動")
            print(f"  直接進入主程式...")
            wifi_started = False
        else:
            print(f"\n⚠️  上次運行異常或首次啟動")
            print(f"  啟動 WiFi 以便遠程調試...")
            wifi_started = self._start_wifi_and_webrepl()
        
        # 重要: 進入主程式前先設置為 False
        print(f"\n🔄 設置 loop_one_success = False")
        self.cfg.set_state('loop_one_success', False)
        
        print("="*70 + "\n")
        
        return wifi_started
    
    def _start_wifi_and_webrepl(self):
        """
        啟動 WiFi 和 WebREPL,等待連接
        
        Returns:
            bool: 是否成功啟動
        """
        try:
            # 讀取網絡配置
            network_config = {
                'enable': self.cfg.get('Network.enable', default=1),
                'pcName': self.cfg.get('Network.pcName', default='esp32'),
                'ssid': self.cfg.get('Network.ssid', default='00'),
                'password': self.cfg.get('Network.password', default='00')
            }
            
            # 檢查是否啟用網絡
            if not network_config['enable']:
                print("  ⚠️  網絡功能已禁用,跳過")
                return False
            
            # 創建 WiFi 管理器
            print(f"\n📡 啟動 WiFi...")
            self.wifi = WiFiManager(
                config_dict=network_config,
                max_retries=3  # 減少重試次數,加快啟動
            )
            
            # 嘗試連接 (不顯示掃描結果,加快速度)
            if self.wifi.connect(show_scan=False):
                info = self.wifi.get_connection_info()
                print(f"\n✓ WiFi 已連接:")
                print(f"  IP: {info['ip']}")
                print(f"  訪問: http://{info['mdns_name']}")
                
                # 啟動 WebREPL
                self._start_webrepl()
                
                # 等待 WebREPL 連接
                self._wait_for_webrepl()
                
                return True
            else:
                print(f"\n✗ WiFi 連接失敗")
                return False
                
        except Exception as e:
            print(f"\n✗ 啟動 WiFi 時出錯: {e}")
            return False
    
    def _start_webrepl(self):
        """啟動 WebREPL"""
        try:
            import webrepl
            webrepl.start()
            print(f"\n✓ WebREPL 已啟動")
            print(f"  密碼: 請查看 webrepl_cfg.py")
        except ImportError:
            print(f"\n⚠️  WebREPL 模塊不可用")
            print(f"  請執行: import webrepl_setup")
        except Exception as e:
            print(f"\n⚠️  WebREPL 啟動失敗: {e}")
    
    def _wait_for_webrepl(self):
        """等待 WebREPL 連接"""
        print(f"\n⏳ 等待 WebREPL 連接 ({self.webrepl_timeout} 秒)...")
        print(f"  使用 WebREPL 客戶端連接進行調試")
        print(f"  或按 Ctrl+C 跳過等待")
        
        start_time = time.time()
        
        try:
            while time.time() - start_time < self.webrepl_timeout:
                remaining = self.webrepl_timeout - int(time.time() - start_time)
                
                # 每5秒顯示一次剩餘時間
                if remaining % 5 == 0:
                    print(f"  ⏱️  剩餘 {remaining} 秒...")
                
                time.sleep(1)
            
            print(f"\n⏱️  等待超時,繼續啟動...")
            
        except KeyboardInterrupt:
            print(f"\n\n⏭️  用戶跳過等待,繼續啟動...")
    
    def mark_loop_success(self):
        """
        標記 loop 成功完成
        應在主程式成功完成一個循環後調用
        """
        self.cfg.set_state('loop_one_success', True)
        self.cfg.set_state('last_success_time', time.time())
        print(f"[SmartBoot] ✓ Loop 成功完成")
    
    def mark_loop_error(self, error_msg='unknown'):
        """
        標記 loop 發生錯誤
        
        Args:
            error_msg: 錯誤信息
        """
        self.cfg.set_state('loop_one_success', False)
        self.cfg.set_state('last_error', error_msg)
        self.cfg.set_state('last_error_time', time.time())
        print(f"[SmartBoot] ✗ Loop 錯誤: {error_msg}")
    
    def close(self):
        """關閉管理器"""
        if self.wifi:
            try:
                self.wifi.disconnect()
            except:
                pass
        
        if self.cfg:
            self.cfg.close()
    
    def __enter__(self):
        """支持 with 語句"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 語句"""
        self.close()