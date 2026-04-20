# 面向知识增强的语音问答 Agent 设计与优化

**学院**：计算机科学与技术学院

**专业**：软件工程

**学生姓名**：黄志栋

**学号**：2251760

---

## 摘要

随着大语言模型技术的快速发展，基于语音交互的智能问答系统在专业领域具有广阔的应用前景。本文设计并实现了一个面向航空维修领域的知识增强语音问答 Agent 系统，集成了语音识别（STT）、检索增强生成（RAG）、大语言模型推理（LLM）和语音合成（TTS）四大核心模块，采用端到端流式架构实现了低延迟的实时语音交互。

在检索增强生成方面，本文构建了基于 5 份飞机维修手册、共 1478 个文档片段的专业知识库，实现了稠密向量检索（FAISS）与稀疏检索（BM25）相结合的混合检索策略，并通过交叉编码器重排序、查询改写、上下文增强切分和航空术语自定义词典等多项优化措施，将检索命中率（Hit Rate@5）从 73.33% 提升至 95.56%，平均倒数排名（MRR@5）从 0.5781 提升至 0.9444。

在流式交互方面，本文基于 FastAPI + WebSocket 架构，通过 asyncio 协程与多线程混合调度模型实现了 STT、LLM 和 TTS 的全链路流式并行处理，配合文本缓冲策略和音频预缓冲机制，将端到端延迟从约 5.6 秒降低至约 1.6 秒。同时实现了基于 VAD 的语音打断功能，提升了交互自然度。

系统前端基于原生 JavaScript 和 Web Audio API 实现了航空仪表盘风格的交互界面，支持持续监听和按住说话两种录音模式。实验结果表明，本系统在检索准确性、响应延迟和交互体验等方面达到了预期目标，能够为航空维修技术人员提供高效、准确的语音问答服务。

**关键词**：检索增强生成；大语言模型；语音交互；混合检索；流式处理

---

## Abstract

With the rapid development of large language model technology, voice-interactive intelligent question-answering systems have broad application prospects in professional domains. This paper designs and implements a knowledge-enhanced voice question-answering Agent system for the aviation maintenance domain, integrating four core modules: Speech-to-Text (STT), Retrieval-Augmented Generation (RAG), Large Language Model inference (LLM), and Text-to-Speech (TTS), employing an end-to-end streaming architecture to achieve low-latency real-time voice interaction.

In terms of retrieval-augmented generation, this paper constructs a professional knowledge base from five aircraft maintenance manuals totaling 1478 document chunks, implements a hybrid retrieval strategy combining dense vector retrieval (FAISS) and sparse retrieval (BM25), and improves the Hit Rate@5 from 73.33% to 95.56% and MRR@5 from 0.5781 to 0.9444 through multiple optimization measures including cross-encoder reranking, query rewriting, contextual chunking enrichment, and custom aviation terminology dictionaries.

In terms of streaming interaction, this paper implements full-pipeline streaming parallel processing of STT, LLM, and TTS based on a FastAPI + WebSocket architecture with an asyncio coroutine and multi-threading hybrid scheduling model, reducing end-to-end latency from approximately 5.6 seconds to approximately 1.6 seconds through text buffering strategies and audio pre-buffering mechanisms. A VAD-based voice interruption feature is also implemented to enhance interaction naturalness.

The system frontend implements an aviation dashboard-styled interactive interface using native JavaScript and Web Audio API, supporting both continuous listening and push-to-talk recording modes. Experimental results demonstrate that the system achieves expected targets in retrieval accuracy, response latency, and interaction experience, providing efficient and accurate voice question-answering services for aviation maintenance technicians.

**Keywords**: Retrieval-Augmented Generation; Large Language Model; Voice Interaction; Hybrid Retrieval; Streaming Processing

---

## 目录

- 第一章 引言
  - 1.1 研究背景与意义
  - 1.2 国内外研究现状
    - 1.2.1 检索增强生成技术研究现状
    - 1.2.2 语音交互技术研究现状
    - 1.2.3 流式交互优化研究现状
  - 1.3 本文主要工作
  - 1.4 本文组织结构
- 第二章 相关技术
  - 2.1 检索增强生成（RAG）
    - 2.1.1 RAG 基本原理
    - 2.1.2 文档切分策略
    - 2.1.3 向量检索
    - 2.1.4 BM25 稀疏检索
    - 2.1.5 混合检索与 RRF 融合
    - 2.1.6 交叉编码器重排序
  - 2.2 大语言模型（LLM）
    - 2.2.1 大语言模型概述
    - 2.2.2 流式生成
    - 2.2.3 提示工程
  - 2.3 语音识别（STT）
  - 2.4 语音合成（TTS）
  - 2.5 WebSocket 通信协议
  - 2.6 异步编程与并发模型
    - 2.6.1 Python asyncio 协程
    - 2.6.2 多线程与跨线程通信
  - 2.7 前端 Web Audio API
  - 2.8 本章小结
- 第三章 系统需求分析与设计
  - 3.1 需求分析
    - 3.1.1 功能需求
    - 3.1.2 非功能需求
    - 3.1.3 用例分析
  - 3.2 系统总体架构设计
    - 3.2.1 系统架构概述
    - 3.2.2 端到端流式架构
    - 3.2.3 线程与协程混合调度模型
  - 3.3 模块设计
    - 3.3.1 STT 语音识别模块
    - 3.3.2 RAG 检索模块
    - 3.3.3 LLM 推理模块
    - 3.3.4 TTS 语音合成模块
    - 3.3.5 Pipeline 编排模块
    - 3.3.6 WebSocket 服务模块
    - 3.3.7 前端模块
  - 3.4 数据设计
    - 3.4.1 文档数据结构
    - 3.4.2 索引数据结构
    - 3.4.3 评估数据结构
  - 3.5 本章小结
- 第四章 系统实现
  - 4.1 开发环境与技术选型
    - 4.1.1 开发环境
    - 4.1.2 核心依赖
    - 4.1.3 云服务接口
  - 4.2 文档预处理与索引构建
    - 4.2.1 PDF 文本提取
    - 4.2.2 文档智能切分
    - 4.2.3 索引构建
  - 4.3 STT 语音识别模块实现
    - 4.3.1 NLS Token 管理
    - 4.3.2 流式识别实现
  - 4.4 LLM 推理模块实现
    - 4.4.1 流式生成实现
    - 4.4.2 提示模板设计
  - 4.5 TTS 语音合成模块实现
    - 4.5.1 双向流式合成
    - 4.5.2 航空型号数字预处理
    - 4.5.3 跨线程音频投递
  - 4.6 Pipeline 编排模块实现
    - 4.6.1 查询处理流程
    - 4.6.2 文本缓冲策略
  - 4.7 WebSocket 服务实现
    - 4.7.1 连接管理与消息路由
    - 4.7.2 AudioBuffer 实现
    - 4.7.3 打断机制实现
  - 4.8 前端界面实现
    - 4.8.1 界面设计
    - 4.8.2 音频采集与处理
    - 4.8.3 音频播放与预缓冲
    - 4.8.4 VAD 语音打断
  - 4.9 本章小结
- 第五章 系统优化
  - 5.1 RAG 检索优化
    - 5.1.1 混合检索策略
    - 5.1.2 交叉编码器重排序
    - 5.1.3 查询改写
    - 5.1.4 上下文增强切分
    - 5.1.5 航空术语自定义词典
    - 5.1.6 元数据过滤
  - 5.2 流式交互优化
    - 5.2.1 端到端流式并行处理
    - 5.2.2 文本缓冲策略优化
    - 5.2.3 音频预缓冲策略
    - 5.2.4 AudioBuffer 批量发送
    - 5.2.5 语音打断机制
    - 5.2.6 STT 静音容忍优化
  - 5.3 本章小结
- 第六章 系统测试与结果分析
  - 6.1 测试环境
  - 6.2 单元测试
    - 6.2.1 RAG 评估指标测试
    - 6.2.2 BM25 索引测试
    - 6.2.3 查询改写测试
    - 6.2.4 元数据提取测试
    - 6.2.5 STT 配置测试
    - 6.2.6 单元测试结果
  - 6.3 端到端测试
    - 6.3.1 测试方案
    - 6.3.2 测试流程
    - 6.3.3 测试结果
  - 6.4 RAG 检索性能评估
    - 6.4.1 评估方法
    - 6.4.2 对比实验设计
    - 6.4.3 实验结果
    - 6.4.4 结果分析
  - 6.5 延迟性能分析
    - 6.5.1 各模块延迟分解
    - 6.5.2 端到端延迟
  - 6.6 本章小结
- 第七章 结论与展望
  - 7.1 工作总结
  - 7.2 不足分析
  - 7.3 未来展望
- 参考文献
- 致谢
