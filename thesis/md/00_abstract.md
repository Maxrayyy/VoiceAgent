# 面向知识增强的语音问答 Agent 设计与优化

**学院**：计算机科学与技术学院

**专业**：软件工程

**学生姓名**：黄志栋

**学号**：2251760

---

## 摘要

随着大语言模型技术的快速发展，基于语音交互的智能问答系统在专业领域具有广阔的应用前景。本文设计并实现了一个面向航空维修领域的知识增强语音问答智能体，集成了语音识别（STT）、检索增强生成（RAG）、大语言模型推理（LLM）和语音合成（TTS）四大核心模块，采用端到端流式架构实现了低延迟的实时语音交互。

在检索增强生成方面，本文构建了基于 5 份飞机维修手册、共 1478 个文档片段的专业知识库，实现了稠密向量检索（FAISS）与稀疏检索（BM25）相结合的混合检索策略，并通过交叉编码器重排序、查询改写、上下文增强切分和航空术语自定义词典等多项优化措施，将检索命中率（Hit Rate@5）从 73.33% 提升至 95.56%，平均倒数排名（MRR@5）从 0.5781 提升至 0.9444。

在流式交互方面，本项目基于 WebSocket 架构，通过多协程与多线程混合调度模型实现了 STT、LLM 和 TTS 的全链路流式并行处理，配合文本缓冲策略和音频预缓冲机制，将端到端延迟从约 5.6 秒降低至约 1.6 秒。同时实现了基于语音活动检测（VAD）的语音打断功能，提升了交互自然度。

实验结果表明，本系统在检索准确性、响应延迟和交互体验等方面达到了预期目标，能够为航空维修技术人员提供高效、准确的语音问答服务。

**关键词**：检索增强生成；大语言模型；语音交互；流式处理

---

## Abstract

With the rapid development of large language model technology, voice-interactive intelligent question-answering systems have broad application prospects in professional domains. This paper designs and implements a knowledge-enhanced voice question-answering intelligent agent for the aviation maintenance domain, integrating four core modules: Speech-to-Text (STT), Retrieval-Augmented Generation (RAG), Large Language Model inference (LLM), and Text-to-Speech (TTS), and adopts an end-to-end streaming architecture to achieve low-latency real-time voice interaction.

In terms of retrieval-augmented generation, this paper constructs a professional knowledge base from five aircraft maintenance manuals totaling 1478 document chunks, implements a hybrid retrieval strategy combining dense vector retrieval (FAISS) and sparse retrieval (BM25), and improves the Hit Rate@5 from 73.33% to 95.56% and MRR@5 from 0.5781 to 0.9444 through multiple optimization measures including cross-encoder reranking, query rewriting, contextual chunking enrichment, and custom aviation terminology dictionaries.

In terms of streaming interaction, the project is built on a WebSocket-based architecture and employs a hybrid scheduling model combining multiple coroutines and multiple threads to realize full-pipeline streaming parallel processing of STT, LLM, and TTS. Together with text buffering and audio pre-buffering strategies, the end-to-end latency is reduced from approximately 5.6 seconds to approximately 1.6 seconds. In addition, a voice interruption mechanism based on Voice Activity Detection (VAD) is implemented to improve interaction naturalness.

Experimental results demonstrate that the system achieves the expected goals in retrieval accuracy, response latency, and interaction experience, and can provide efficient and accurate voice question-answering services for aviation maintenance technicians.

**Keywords**: Retrieval-Augmented Generation; Large Language Model; Voice Interaction; Streaming Processing

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
- 第二章 技术选型
  - 2.1 检索增强生成（RAG）
    - 2.1.1 RAG 基本原理
    - 2.1.2 文档切分策略
    - 2.1.3 向量检索
    - 2.1.4 BM25 稀疏检索与混合检索
    - 2.1.5 交叉编码器重排序
  - 2.2 大语言模型（LLM）
    - 2.2.1 大语言模型概述
    - 2.2.2 流式生成
    - 2.2.3 提示工程
  - 2.3 语音交互与实时通信
    - 2.3.1 语音识别（STT）
    - 2.3.2 语音合成（TTS）
    - 2.3.3 异步并发模型与 WebSocket 通信
  - 2.4 本章小结
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
    - 3.3.1 RAG 检索模块
    - 3.3.2 STT 语音识别模块
    - 3.3.3 LLM 推理模块
    - 3.3.4 TTS 语音合成模块
    - 3.3.5 会话编排与服务接入模块
  - 3.4 数据设计
    - 3.4.1 文档数据结构
    - 3.4.2 索引数据结构
    - 3.4.3 评估数据结构
  - 3.5 本章小结
- 第四章 系统实现
  - 4.1 系统总体实现
    - 4.1.1 开发环境与技术选型
    - 4.1.2 系统总体架构
    - 4.1.3 模块划分与功能职责
    - 4.1.4 端到端处理流程
  - 4.2 RAG 检索模块实现
    - 4.2.1 文档预处理
    - 4.2.2 索引构建
    - 4.2.3 混合检索与重排序
  - 4.3 STT 语音识别模块实现
    - 4.3.1 NLS Token 管理
    - 4.3.2 流式识别与线程隔离
  - 4.4 LLM 推理模块实现
    - 4.4.1 流式生成实现
    - 4.4.2 提示模板设计
  - 4.5 TTS 语音合成模块实现
    - 4.5.1 双向流式合成
    - 4.5.2 航空型号数字预处理
    - 4.5.3 跨线程音频投递
  - 4.6 会话编排与服务接入模块实现
    - 4.6.1 会话建立与消息接入
    - 4.6.2 查询编排与上下文维护
    - 4.6.3 文本缓冲、音频批量发送与打断控制
  - 4.7 本章小结
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
    - 5.2.4 音频批量发送
    - 5.2.5 语音打断机制
    - 5.2.6 STT 静音容忍优化
  - 5.3 本章小结
- 第六章 系统测试与结果分析
  - 6.1 测试环境
    - 6.1.1 硬件与软件环境
    - 6.1.2 测试数据
  - 6.2 单元测试
  - 6.3 端到端测试
    - 6.3.1 测试方案
    - 6.3.2 测试流程
    - 6.3.3 测试结果
  - 6.4 RAG 检索性能评估
    - 6.4.1 评估方法
    - 6.4.2 对比实验设计
    - 6.4.3 实验结果
  - 6.5 延迟性能分析
    - 6.5.1 各模块延迟分解
    - 6.5.2 端到端延迟测量方法与结果
  - 6.6 本章小结
- 第七章 总结与展望
  - 7.1 工作总结
  - 7.2 不足分析
  - 7.3 未来展望
- 参考文献
- 致谢
