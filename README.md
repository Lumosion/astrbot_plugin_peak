# AstrBot PEAK 每日地图插件

通过 `/peak` 获取 PEAK 今日地图。

通过 `/peak 变体` 查看全部地图区域、默认状态、变体名称和简单说明。

通过 `/peak 图鉴 <区域>` 查看单个区域的特色、危险与变体详情。

## 指令

### 仅查看地图

```text
/peak
```

默认只显示：

- 今日日期
- 每日地图类型
- 对应的变体名称
- 每个区域的简单介绍
- 一张包含各地图类型图标的汇总图片

### 查看全部变体总表

```text
/peak 变体
```

列出全部 10 个区域及其变体名称与说明。

### 查看单个区域图鉴

```text
/peak 图鉴 海岸
/peak 海岸
```

显示该区域的简介、特色（features）、危险（hazards）与变体（variants）详情。

可用区域名：海岸、雨林、森蕈、雪山、方山、火山、雾沼、熔炉、城塞、顶峰。

## 特点

- 不接入 AI / LLM
- 直接从 PEAK 游略网站抓取数据
- 内置完整区域图鉴（特色 / 危险 / 变体）
- 使用网页图标素材生成每日地图汇总图片
- 异步 HTTP 请求
- 网站异常时会返回错误信息

## 安装

将 `astrbot_plugin_peak` 文件夹放到：

```text
AstrBot/data/plugins/
```

安装依赖：

```bash
pip install -r requirements.txt
```

然后重启 AstrBot。

不要直接执行 `main.py`。它是 AstrBot 加载的插件入口，不是独立运行脚本；直接执行会因为当前 Python 环境没有 AstrBot 宿主模块而出现 `No module named 'astrbot'`。

## 数据源

https://youlue.top/peak/
