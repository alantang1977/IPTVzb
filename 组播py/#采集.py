import os
import requests
import re
import base64
import cv2
import datetime
import time
import random
from bs4 import BeautifulSoup

# 定义请求头
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/118.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
]

# 定义FOFA搜索配置
FOFA_CONFIG = {
    "base_url": "https://fofa.info/result?qbase64=",
    "timeout": 30,
    "max_retries": 5,
    "retry_delay": 5,  # 初始重试延迟秒数
    "max_delay": 30,   # 最大重试延迟秒数
    "proxies": {
        # "http": "http://127.0.0.1:8080",
        # "https": "http://127.0.0.1:8080"
    }  # 如需使用代理，取消注释并配置
}

# 定义频道分类规则
def classify_channel(channel_name):
    guangdong_channels = ['广州综合', '广州新闻', '广东珠江', '广州影视频道', '广东综艺', '广东影视']
    hkgmta_channels = ['翡翠台', '凤凰中文', '凤凰资讯', '明珠台', '娱乐新闻台', '无线新闻台', '有线新闻', '中天新闻', '星空卫视']
    
    if channel_name.startswith('CCTV'):
        return '央视频道'
    elif any(province in channel_name for province in ['北京', '江苏', '浙江', '东方', '深圳', '安徽', '河南', '黑龙江', '山东', '天津', '四川', '重庆', '湖北', '江西', '贵州', '东南', '云南', '河北', '海南', '吉林', '辽宁']):
        return '地方卫视'
    elif any(channel in channel_name for channel in guangdong_channels):
        return '广东频道'
    elif any(channel in channel_name for channel in hkgmta_channels):
        return '港澳台频道'
    else:
        return '其他频道'

# 从rtp目录获取文件名
def get_provinces_isps():
    files = os.listdir('rtp')
    files_name = []
    for file in files:
        name, extension = os.path.splitext(file)
        files_name.append(name)
    provinces_isps = [name for name in files_name if name.count('_') == 1]
    return provinces_isps

# 获取关键词列表
def get_keywords(provinces_isps):
    keywords = []
    for province_isp in provinces_isps:
        try:
            with open(f'rtp/{province_isp}.txt', 'r', encoding='utf-8') as file:
                lines = file.readlines()
                lines = [line.strip() for line in lines if line.strip()]
            if lines:
                first_line = lines[0]
                if "rtp://" in first_line:
                    mcast = first_line.split("rtp://")[1].split(" ")[0]
                    keywords.append(province_isp + "_" + mcast)
        except FileNotFoundError:
            print(f"文件 '{province_isp}.txt' 不存在. 跳过此文件.")
    return keywords

# 根据isp获取org值
def get_org(province, isp):
    if province == "北京" and isp == "联通":
        isp_en = "cucc"
        org = "China Unicom Beijing Province Network"
    elif isp == "联通":
        isp_en = "cucc"
        org = "CHINA UNICOM China169 Backbone"
    elif isp == "电信":
        org = "Chinanet"
        isp_en = "ctcc"
    elif isp == "移动":
        org = "China Mobile communications corporation"
        isp_en = "cmcc"
    else:
        org = ""
    return org, isp_en

# 从fofa获取结果URL
def get_result_urls(keyword):
    province, isp, mcast = keyword.split("_")
    org, isp_en = get_org(province, isp)
    current_time = datetime.datetime.now()
    timeout_cnt = 0
    result_urls = set()
    
    while len(result_urls) == 0 and timeout_cnt <= FOFA_CONFIG["max_retries"]:
        try:
            # 随机选择User-Agent
            header = {"User-Agent": random.choice(USER_AGENTS)}
            
            # 构建搜索URL
            search_txt = f'\"udpxy\" && country=\"CN\" && region=\"{province}\" && org=\"{org}\"'
            bytes_string = search_txt.encode('utf-8')
            search_txt_encoded = base64.b64encode(bytes_string).decode('utf-8')
            search_url = FOFA_CONFIG["base_url"] + search_txt_encoded
            
            print(f"{current_time} 查询运营商 : {province}{isp} ，查询网址 : {search_url}")
            
            # 发送请求
            response = requests.get(
                search_url, 
                headers=header, 
                timeout=FOFA_CONFIG["timeout"],
                proxies=FOFA_CONFIG["proxies"]
            )
            response.raise_for_status()
            
            # 解析响应
            html_content = response.text
            html_soup = BeautifulSoup(html_content, "html.parser")
            
            # 提取URL
            pattern = r"http://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+"
            urls_all = re.findall(pattern, html_content)
            result_urls = set(urls_all)
            
            print(f"{current_time} 找到 {len(result_urls)} 个潜在IP地址")
            
        except requests.exceptions.RequestException as e:
            print(f"{current_time} 请求出错 (尝试 {timeout_cnt+1}/{FOFA_CONFIG['max_retries']}): {e}")
            timeout_cnt += 1
            
            # 指数退避策略
            delay = min(FOFA_CONFIG["retry_delay"] * (2 ** timeout_cnt), FOFA_CONFIG["max_delay"])
            delay += random.uniform(0, 2)  # 添加随机抖动
            print(f"{current_time} 等待 {delay:.2f} 秒后重试...")
            time.sleep(delay)
            
        except Exception as e:
            print(f"{current_time} 发生未知错误: {e}")
            timeout_cnt += 1
            time.sleep(FOFA_CONFIG["retry_delay"])
    
    return result_urls, province, isp, mcast

# 验证IP是否有效
def validate_ips(result_urls, mcast):
    current_time = datetime.datetime.now()
    valid_ips = []
    
    # 设置OpenCV优化
    cv2.setUseOptimized(True)
    cv2.setNumThreads(4)
    
    for url in result_urls:
        video_url = url + "/rtp/" + mcast
        try:
            print(f"{current_time} 正在验证: {video_url}")
            
            # 设置视频捕获超时
            cap = cv2.VideoCapture(video_url)
            
            # 尝试读取一帧，设置超时机制
            start_time = time.time()
            ret = False
            
            while (time.time() - start_time) < 10:  # 10秒超时
                ret = cap.grab()  # 快速获取帧，不解码
                if ret:
                    break
                time.sleep(0.1)
            
            if not ret:
                print(f"{current_time} {video_url} 连接超时或无效")
            else:
                # 获取视频信息
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                
                print(f"{current_time} {video_url} 有效 - 分辨率: {width}x{height}, FPS: {fps:.1f}")
                
                if width > 0 and height > 0:
                    valid_ips.append(url)
            
            cap.release()
            
        except Exception as e:
            print(f"{current_time} 验证 {video_url} 时出错: {e}")
            if 'cap' in locals() and cap.isOpened():
                cap.release()
    
    return valid_ips

# 生成播放列表文件
def generate_playlist(valid_ips, province, isp):
    rtp_filename = f'rtp/{province}_{isp}.txt'
    try:
        with open(rtp_filename, 'r', encoding='utf-8') as file:
            data = file.read()
    except FileNotFoundError:
        print(f"错误: 文件 {rtp_filename} 不存在")
        return None
    
    txt_filename = f'{province}{isp}.txt'
    with open(txt_filename, 'w') as new_file:
        for url in valid_ips:
            new_data = data.replace("rtp://", f"{url}/rtp/")
            new_file.write(new_data)
    print(f'已生成播放列表，保存至{txt_filename}')
    return txt_filename

# 生成m3u文件
def generate_m3u(txt_filename, province, isp):
    try:
        with open(txt_filename, 'r') as input_file:
            lines = input_file.readlines()
    except FileNotFoundError:
        print(f"错误: 文件 {txt_filename} 不存在")
        return
    
    lines = [line for line in lines if line.count(',') == 1]
    m3u_filename = f'{province}{isp}.m3u'
    
    with open(m3u_filename, 'w', encoding='utf-8') as output_file:
        output_file.write('#EXTM3U  x-tvg-url="https://live.fanmingming.com/e.xml"\n')
        
        for line in lines:
            parts = line.strip().split(',')
            if len(parts) != 2:
                continue
                
            name1 = parts[0]
            # 规范化频道名称
            uppercase_name1 = name1.upper()
            name1 = uppercase_name1
            name1 = name1.replace("中央", "CCTV")
            name1 = name1.replace("高清", "")
            name1 = name1.replace("HD", "")
            name1 = name1.replace("标清", "")
            name1 = name1.replace("频道", "")
            name1 = name1.replace("-", "")
            name1 = name1.replace("_", "")
            name1 = name1.replace(" ", "")
            name1 = name1.replace("PLUS", "+")
            name1 = name1.replace("＋", "+")
            name1 = name1.replace("(", "")
            name1 = name1.replace(")", "")
            name1 = name1.replace("CCTV1综合", "CCTV1")
            name1 = name1.replace("CCTV2财经", "CCTV2")
            name1 = name1.replace("CCTV3综艺", "CCTV3")
            name1 = name1.replace("CCTV4国际", "CCTV4")
            name1 = name1.replace("CCTV4中文国际", "CCTV4")
            name1 = name1.replace("CCTV5体育", "CCTV5")
            name1 = name1.replace("CCTV6电影", "CCTV6")
            name1 = name1.replace("CCTV7军事", "CCTV7")
            name1 = name1.replace("CCTV7军农", "CCTV7")
            name1 = name1.replace("CCTV7国防军事", "CCTV7")
            name1 = name1.replace("CCTV8电视剧", "CCTV8")
            name1 = name1.replace("CCTV9记录", "CCTV9")
            name1 = name1.replace("CCTV9纪录", "CCTV9")
            name1 = name1.replace("CCTV10科教", "CCTV10")
            name1 = name1.replace("CCTV11戏曲", "CCTV11")
            name1 = name1.replace("CCTV12社会与法", "CCTV12")
            name1 = name1.replace("CCTV13新闻", "CCTV13")
            name1 = name1.replace("CCTV新闻", "CCTV13")
            name1 = name1.replace("CCTV14少儿", "CCTV14")
            name1 = name1.replace("CCTV15音乐", "CCTV15")
            name1 = name1.replace("CCTV16奥林匹克", "CCTV16")
            name1 = name1.replace("CCTV17农业农村", "CCTV17")
            name1 = name1.replace("CCTV5+体育赛视", "CCTV5+")
            name1 = name1.replace("CCTV5+体育赛事", "CCTV5+")
            name1 = name1.replace("综合教育", "")
            
            # 分类频道
            category = classify_channel(name1)
            output_file.write(f'#EXTINF:-1 group-title="{category}",{name1}\n{parts[1]}\n')
    
    print(f'已生成m3u文件，保存至{m3u_filename}')

# 主函数
def main():
    print("开始IPTV频道采集...")
    
    # 确保rtp目录存在
    if not os.path.exists('rtp'):
        print("错误: 'rtp' 目录不存在，请创建该目录并添加组播源文件")
        return
    
    # 获取省份和运营商列表
    provinces_isps = get_provinces_isps()
    print(f"本次查询：{provinces_isps}的组播节目")
    
    # 获取关键词列表
    keywords = get_keywords(provinces_isps)
    if not keywords:
        print("错误: 未找到有效的组播源文件")
        return
    
    # 处理每个关键词
    for keyword in keywords:
        print(f"\n===== 处理 {keyword} =====")
        
        # 从FOFA获取结果URL
        result_urls, province, isp, mcast = get_result_urls(keyword)
        
        if not result_urls:
            print(f"警告: 未从FOFA找到任何结果，跳过 {province}{isp}")
            continue
        
        # 验证IP有效性
        valid_ips = validate_ips(result_urls, mcast)
        
        if valid_ips:
            # 生成播放列表
            txt_filename = generate_playlist(valid_ips, province, isp)
            if txt_filename:
                # 生成m3u文件
                generate_m3u(txt_filename, province, isp)
        else:
            print(f"警告: 未找到有效IP地址，跳过 {province}{isp}")
    
    print("\nIPTV频道采集完成!")

if __name__ == "__main__":
    main()
