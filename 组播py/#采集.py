import os
import requests
import re
import base64
import cv2
from datetime import datetime
from bs4 import BeautifulSoup

def get_province_isp_files(rtp_dir="rtp"):
    """获取rtp目录下省份_运营商的文件名（无后缀）"""
    files = os.listdir(rtp_dir)
    files_name = [os.path.splitext(f)[0] for f in files]
    provinces_isps = [name for name in files_name if name.count('_') == 1]
    return provinces_isps

def extract_mcast_keywords(provinces_isps, rtp_dir="rtp"):
    """从每个文件第一行提取mcast地址，生成 province_isp_mcast 列表"""
    keywords = []
    for province_isp in provinces_isps:
        txt_path = os.path.join(rtp_dir, f'{province_isp}.txt')
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
            if lines and "rtp://" in lines[0]:
                mcast = lines[0].split("rtp://")[1].split(" ")[0]
                keywords.append(f"{province_isp}_{mcast}")
        except FileNotFoundError:
            print(f"文件 '{province_isp}.txt' 不存在，跳过。")
    return keywords

def get_isp_info(province, isp):
    """根据省份和运营商返回 isp_en 和 org 信息"""
    if province == "北京" and isp == "联通":
        return "cucc", "China Unicom Beijing Province Network"
    elif isp == "联通":
        return "cucc", "CHINA UNICOM China169 Backbone"
    elif isp == "电信":
        return "ctcc", "Chinanet"
    elif isp == "移动":
        return "cmcc", "China Mobile communications corporation"
    else:
        return "", ""

def search_udpxy_ips(province, isp, org, max_retry=5):
    """通过Fofa搜索udpxy代理IP"""
    search_txt = f'"udpxy" && country="CN" && region="{province}" && org="{org}"'
    search_b64 = base64.b64encode(search_txt.encode('utf-8')).decode('utf-8')
    search_url = f'https://fofa.info/result?qbase64={search_b64}'
    current_time = datetime.now()
    timeout_cnt = 0
    while timeout_cnt < max_retry:
        try:
            print(f"{current_time} 查询运营商: {province}{isp}, 查询网址: {search_url}")
            resp = requests.get(search_url, timeout=30)
            resp.raise_for_status()
            html_content = resp.text
            # 匹配 http://IP:PORT
            urls = set(re.findall(r"http://\d{1,3}(?:\.\d{1,3}){3}:\d+", html_content))
            print(f"{current_time} 搜索结果: {urls}")
            if urls:
                return urls
            else:
                print(f"{current_time} 未找到可用IP, 重试...")
        except (requests.Timeout, requests.RequestException) as e:
            timeout_cnt += 1
            print(f"{current_time} [{province}] 搜索请求异常：{e}，第{timeout_cnt}次重试。")
    print(f"{current_time} 搜索IPTV频道源[{province}{isp}]，超时/异常次数过多，停止处理。")
    return set()

def test_video_urls(result_urls, mcast):
    """测试udpxy代理下的rtp流是否可用，返回可用IP列表"""
    valid_ips = []
    for url in result_urls:
        video_url = f"{url}/rtp/{mcast}"
        try:
            cap = cv2.VideoCapture(video_url)
            if not cap.isOpened():
                print(f"{datetime.now()} {video_url} 无效")
            else:
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                print(f"{datetime.now()} {video_url} 分辨率: {width}x{height}")
                if width > 0 and height > 0:
                    valid_ips.append(url)
                cap.release()
        except Exception as e:
            print(f"读取视频流异常: {e}")
    return valid_ips

def generate_txt_and_m3u(province, isp, mcast, valid_ips, rtp_dir="rtp"):
    """生成txt和m3u播放列表文件"""
    rtp_filename = os.path.join(rtp_dir, f'{province}_{isp}.txt')
    if not os.path.exists(rtp_filename):
        print(f"源文件 {rtp_filename} 不存在，无法生成播放列表。")
        return
    with open(rtp_filename, 'r', encoding='utf-8') as f:
        data = f.read()
    txt_filename = f"{province}{isp}.txt"
    with open(txt_filename, 'w', encoding='utf-8') as f:
        for url in valid_ips:
            new_data = data.replace("rtp://", f"{url}/rtp/")
            f.write(new_data)
    print(f"已生成播放列表，保存至 {txt_filename}")

    # 频道分组
    group_cctv = ["CCTV1", "CCTV2", "CCTV3", "CCTV4", "CCTV5", "CCTV5+", "CCTV6", "CCTV7", "CCTV8", "CCTV9", "CCTV10", "CCTV11", "CCTV12", "CCTV13", "CCTV14", "CCTV15", "CCTV16", "CCTV17"]
    group_shuzi = ["CHC动作电影", "CHC家庭影院", "CHC高清电影", "重温经典", "第一剧场", "风云剧场", "怀旧剧场", "世界地理", "发现之旅"]
    group_jiaoyu = ["CETV1", "CETV2", "CETV3", "CETV4", "山东教育", "早期教育"]
    group_weishi = ["北京卫视", "湖南卫视", "东方卫视", "四川卫视", "天津卫视", "安徽卫视", "山东卫视", "广东卫视", "广西卫视", "江苏卫视"]

    # 生成m3u
    m3u_filename = f"{province}{isp}.m3u"
    with open(txt_filename, 'r', encoding='utf-8') as input_file:
        lines = input_file.readlines()
    lines = [l for l in lines if l.count(',') == 1]
    with open(m3u_filename, 'w', encoding='utf-8') as output_file:
        output_file.write('#EXTM3U x-tvg-url="https://live.fanmingming.com/e.xml"\n')
        for line in lines:
            parts = line.strip().split(',')
            name = parts[0]
            url = parts[1]
            name1 = name.upper()
            name1 = name1.replace("中央", "CCTV").replace("高清", "").replace("HD", "") \
                .replace("标清", "").replace("频道", "").replace("-", "").replace("_", "") \
                .replace(" ", "").replace("PLUS", "+").replace("＋", "+") \
                .replace("(", "").replace(")", "")
            # 主要频道替换
            name1 = name1.replace("CCTV1综合", "CCTV1").replace("CCTV2财经", "CCTV2").replace("CCTV3综艺", "CCTV3")
            name1 = name1.replace("CCTV4国际", "CCTV4").replace("CCTV4中文国际", "CCTV4").replace("CCTV5体育", "CCTV5")
            name1 = name1.replace("CCTV6电影", "CCTV6").replace("CCTV7军事", "CCTV7").replace("CCTV7军农", "CCTV7")
            name1 = name1.replace("CCTV7国防军事", "CCTV7").replace("CCTV8电视剧", "CCTV8").replace("CCTV9记录", "CCTV9")
            name1 = name1.replace("CCTV9纪录", "CCTV9").replace("CCTV10科教", "CCTV10").replace("CCTV11戏曲", "CCTV11")
            name1 = name1.replace("CCTV12社会与法", "CCTV12").replace("CCTV13新闻", "CCTV13").replace("CCTV新闻", "CCTV13")
            name1 = name1.replace("CCTV14少儿", "CCTV14").replace("CCTV15音乐", "CCTV15").replace("CCTV16奥林匹克", "CCTV16")
            name1 = name1.replace("CCTV17农业农村", "CCTV17").replace("CCTV5+体育赛视", "CCTV5+").replace("CCTV5+体育赛事", "CCTV5+")
            # 其他杂项
            name1 = name1.replace("综合教育", "").replace("空中课堂", "").replace("教育服务", "").replace("职业教育", "")
            name1 = name1.replace("Documentary", "记录").replace("Français", "法语").replace("Русский", "俄语")
            name1 = name1.replace("Español", "西语").replace("العربية", "阿语").replace("NewTv", "")
            name1 = name1.replace("CCTV兵器科技", "兵器科技").replace("CCTV怀旧剧场", "怀旧剧场")
            name1 = name1.replace("CCTV世界地理", "世界地理").replace("CCTV文化精品", "文化精品").replace("CCTV央视台球", "央视台球")
            name1 = name1.replace("CCTV央视高网", "央视高网").replace("CCTV风云剧场", "风云剧场").replace("CCTV第一剧场", "第一剧场")
            name1 = name1.replace("CCTV风云足球", "风云足球").replace("CCTV电视指南", "电视指南").replace("CCTV风云音乐", "风云音乐")
            name1 = name1.replace("CCTV女性时尚", "女性时尚").replace("CHC电影", "CHC高清电影")

            if name1 in group_cctv:
                group_title = "央视频道"
            elif name1 in group_shuzi:
                group_title = "数字频道"
            elif name1 in group_jiaoyu:
                group_title = "教育频道"
            elif name1 in group_weishi:
                group_title = "卫视频道"
            else:
                group_title = "其他频道"

            output_file.write(f'#EXTINF:-1 tvg-id="{name1}" tvg-name="{name1}" tvg-logo="https://live.fanmingming.com/tv/{name1}.png" group-title="{group_title}",{name}\n{url}\n')
    print(f'已保存至 {m3u_filename}')

def main():
    print("扫描rtp目录...")
    provinces_isps = get_province_isp_files()
    print(f"本次查询：{provinces_isps} 的组播节目")
    keywords = extract_mcast_keywords(provinces_isps)
    for keyword in keywords:
        try:
            province, isp, mcast = keyword.split("_")
        except ValueError:
            print(f"分离关键字失败: {keyword}")
            continue
        isp_en, org = get_isp_info(province, isp)
        if not org:
            print(f"{province}{isp} 未识别运营商，跳过。")
            continue
        result_urls = search_udpxy_ips(province, isp, org)
        if not result_urls:
            print(f"{province}{isp} 未找到合适的IP地址。")
            continue
        valid_ips = test_video_urls(result_urls, mcast)
        if not valid_ips:
            print(f"{province}{isp} 没有可用的IP可生成播放列表。")
            continue
        generate_txt_and_m3u(province, isp, mcast, valid_ips)
    print("节目表制作完成！文件输出在当前文件夹！")

if __name__ == '__main__':
    main()
