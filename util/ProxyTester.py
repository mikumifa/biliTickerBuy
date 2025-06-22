import re
import time
import requests
import loguru
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
# 代理连通性测试工具
class ProxyTester:
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
    
    # 测试单个代理连通性
    def test_single_proxy(self, proxy: str) -> Dict[str, Any]:
        result = {
            "proxy": proxy,
            "status": "failed",
            "response_time": None,
            "error": None,
            "ip_info": None
        }
        
        try:
            session = requests.Session()
            session.trust_env = False
            # 配置代理
            if proxy == "none" or proxy.lower() == "direct":
                session.proxies = {}
                result["proxy"] = "直连"
            else:
                if not self._validate_proxy_format(proxy):
                    result["error"] = "代理格式无效"
                    return result
                    
                session.proxies = {
                    "http": proxy,
                    "https": proxy
                }
            
            # 测试连通性和响应时间
            start_time = time.time()
            response = session.get(
                "https://api.bilibili.com/x/web-interface/nav",
                timeout=self.timeout,
                headers={
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
                }
            )
            end_time = time.time()
            response_time = round((end_time - start_time) * 1000, 2)  # 毫秒
            if response.status_code == 200:
                result["status"] = "success"
                result["response_time"] = response_time
            else:
                result["error"] = f"B站连接失败: HTTP {response.status_code}"
                result["status"] = "partial"
                result["response_time"] = response_time
        except requests.exceptions.Timeout:
            result["error"] = f"连接超时 (>{self.timeout}s)"
        except requests.exceptions.ProxyError:
            result["error"] = "代理服务器错误或无法连接"
        except requests.exceptions.ConnectionError as e:
            if "proxy" in str(e).lower():
                result["error"] = "代理连接失败"
            else:
                result["error"] = "网络连接失败"
        except Exception as e:
            result["error"] = f"未知错误: {str(e)}"
        
        return result
    
    # 验证代理格式是否正确
    def _validate_proxy_format(self, proxy: str) -> bool:
        try:
            # 基本格式检查
            if not proxy or proxy.strip() == "":
                return False
            
            # 检查是否包含协议
            if not any(proxy.startswith(protocol) for protocol in ["http://", "https://", "socks5://", "socks4://"]):
                return False
            
            # 检查是否包含端口
            if ":" not in proxy.split("://")[1]:
                return False
                
            return True
        except:
            return False
    # 测试代理列表的连通性
    def test_proxy_list(self, proxy_string: str, max_workers: int = 5) -> List[Dict[str, Any]]:
        if not proxy_string or proxy_string.strip() == "":
            proxy_list = ["none"]
        else:
            proxy_list = [p.strip() for p in proxy_string.split(",") if p.strip()]
            if not proxy_list:
                proxy_list = ["none"]
            else:
                if "none" not in [p.lower() for p in proxy_list] and "direct" not in [p.lower() for p in proxy_list]:
                    proxy_list.insert(0, "none")
        
        results = []
        # 使用线程池并发测试
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_proxy = {
                executor.submit(self.test_single_proxy, proxy): proxy 
                for proxy in proxy_list
            }
            
            for future in as_completed(future_to_proxy):
                try:
                    result = future.result()
                    results.append(result)
                    loguru.logger.info(f"代理测试完成: {result['proxy']} - {result['status']}")
                except Exception as e:
                    loguru.logger.error(f"代理测试异常: {e}")
        # 按照原始顺序排序结果（直连在前，然后是代理）
        def get_sort_key(result):
            proxy = result['proxy']
            if proxy == "直连" or proxy.lower() in ["none", "direct"]:
                return (0, proxy)  
            else:
                try:
                    return (1, proxy_list.index(proxy))
                except ValueError:
                    return (2, proxy)
        results.sort(key=get_sort_key)
        return results
    
    # 格式化测试结果为可读文本
    def format_test_results(self, results: List[Dict[str, Any]]) -> str:
        output = []
        output.append("代理连通性测试结果:")
        output.append("=" * 50)
        
        success_count = 0
        for i, result in enumerate(results, 1):
            proxy = result["proxy"]
            status = result["status"]
            response_time = result["response_time"]
            error = result["error"]
            ip_info = result["ip_info"]
            
            if status == "success":
                output.append(f"✅ [{i}] {proxy}")
                output.append(f"    响应时间: {response_time}ms")
                output.append(f"    出口IP: {ip_info}")
                success_count += 1
            elif status == "partial":
                output.append(f"⚠️  [{i}] {proxy}")
                output.append(f"    响应时间: {response_time}ms")
                output.append(f"    出口IP: {ip_info}")
                output.append(f"    警告: {error}")
            else:
                output.append(f"❌ [{i}] {proxy}")
                output.append(f"    错误: {error}")
            
            output.append("")
        
        output.append("=" * 50)
        output.append(f"测试统计: {success_count}/{len(results)} 个代理可用")
        return "\n".join(output)

def test_proxy_connectivity(proxy_string: str = "none", timeout: int = 10) -> str:
    tester = ProxyTester(timeout=timeout)
    results = tester.test_proxy_list(proxy_string)
    return tester.format_test_results(results)

