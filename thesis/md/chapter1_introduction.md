# 第一章 引言

## 1.1 研究背景与意义

航空维修是典型的适合语音交互的应用场景。技术人员在执行检修任务时，需要频繁查阅维修手册（AMM）、技术通报（SB）和适航指令（AD）等海量技术文档，一架现代民航客机的维修手册往往多达数万页。在高噪声机库、狭窄机身内部或高空作业平台等环境下，传统的纸质手册翻阅或键盘终端检索不仅耗时费力，也严重打断作业节奏。据统计，文档查阅时间可占一次典型检修任务总工时的 20%-30%。因此，构建能够通过语音进行自然对话、从权威知识库中准确回答技术问题的智能助手，对提升维修效率和保障飞行安全具有重要的现实意义。

近年来，以 ChatGPT、GPT-4 为代表的大语言模型（LLM）展现出强大的自然语言理解和生成能力，为智能问答提供了新的技术范式。然而，LLM 存在"幻觉"（Hallucination）问题，即生成看似合理但与事实不符的回答。在航空维修这一安全关键（Safety-Critical）领域，错误的维修指导可能直接导致飞行安全事故——国际民航组织（ICAO）统计显示维修相关因素在航空事故致因中占比约 12%。因此，单纯依赖 LLM 生成能力是不可接受的，回答必须有据可查、来源可追溯。检索增强生成（Retrieval-Augmented Generation, RAG）技术通过在生成前先从权威文档中检索相关内容作为参考依据，有效缓解了幻觉问题，特别适用于航空维修这类对信息准确性要求极高的专业场景。

此外，实时语音交互面临严峻的延迟挑战。传统串行模式下，STT、RAG、LLM、TTS 各阶段时间依次累积，端到端延迟往往超过 5 秒；而研究表明超过 2 秒用户便会明显感受到等待。流式处理（Streaming Processing）技术使得各模块可以并行工作——边识别边返回、边推理边生成、边合成边播放，从而大幅降低响应延迟。基于上述背景，本文设计并实现了一个面向航空维修领域的知识增强语音问答 Agent 系统，采用基于 WebSocket 的端到端流式架构并在 RAG 环节引入多项优化，为维修技术人员提供高效、准确、自然的语音交互式技术咨询工具。

## 1.2 国内外研究现状

### 1.2.1 检索增强生成技术研究现状

RAG 概念由 Lewis 等人于 2020 年提出[1]，开创了"检索+生成"的研究范式。在检索环节，Karpukhin 等人提出的密集向量检索（DPR）[2]使用 BERT 对查询和文档进行稠密编码以实现语义匹配，但在精确术语匹配场景上不如 BM25 等稀疏方法，因此近年来基于 RRF 等融合算法的混合检索受到广泛关注。在检索结果优化方面，Nogueira 和 Cho 提出的 BERT 重排序[3]以及 Glass 等人的 Re2G 框架[4]验证了"检索-重排-生成"三阶段流水线的有效性。针对 LLM 幻觉，Huang 等人的综述[5]将 RAG 列为最有效的缓解手段之一，Xiong 等人[6]则进一步探索了知识图谱增强的 RAG 方法。

### 1.2.2 语音交互技术研究现状

语音识别（ASR）已从 GMM-HMM 发展到端到端深度模型，FunASR[7] 中的 Paraformer 模型采用非自回归并行解码，在保持高精度的同时实现流式识别；阿里云 NLS、百度语音、讯飞开放平台等商业服务也提供了稳定的生产级流式 API。语音合成（TTS）方面，以 CosyVoice[8]为代表的新一代模型基于监督语义 token 生成自然流畅的语音并支持流式合成。对话系统架构上，传统的 NLU/DM/NLG 三模块流水线[9]正逐步被以 LLM 为核心引擎的方案取代，Reddy 等人[10]在医疗问答中验证了 RAG 的有效性，Yang 等人[11]提出的 SpeechRAG 框架则探索了 RAG 与语音交互结合的可行性。

### 1.2.3 流式交互优化研究现状

人机交互研究表明，对话延迟低于 400 毫秒时用户几乎无感，超过 2 秒则明显不自然，超过 5 秒将显著降低满意度。流式处理通过将"等待完成后处理"转变为"边接收边处理"来消除阶段间的等待时间，并配合 WebSocket 全双工协议与 asyncio 等异步编程模型实现高并发数据流管理。然而目前学术界和工业界对流式语音问答系统的架构设计研究仍相对有限，大多数 RAG 工作集中于文本场景，对语音输入/输出、中间结果处理、流式合成、用户打断等特殊需求缺乏系统性探讨，本文工作在一定程度上填补了这一空白。

## 1.3 本文主要工作

（1）**系统架构设计**：设计基于 FastAPI + WebSocket 的端到端流式架构，将 RAG 检索、语音识别、语言模型推理、语音合成与会话编排统一到同一处理链路中，并采用协程与线程混合调度方式保证实时性，将端到端延迟控制在 1-2 秒。

（2）**RAG 知识库构建**：基于 PaddleX PP-DocLayout 版面分析和 PaddleOCR 解决维修手册 PDF 的复杂版面文本提取；实现 300-800 字智能段落切分并自动提取章节与页码元数据；同时构建 FAISS 向量索引和 BM25 稀疏索引。

（3）**RAG 检索优化**：提出并实现五项优化——混合检索与 RRF 融合、gte-rerank 交叉编码器重排序、基于 LLM 的查询改写、上下文增强切分（Contextual Chunking）、航空术语自定义词典。在 1478 个文档片段的知识库上评估，Hit Rate@5 从 73.33% 提升至 95.56%，MRR@5 从 0.5781 提升至 0.9444。

（4）**流式交互优化**：实现 LLM 流式生成与 TTS 流式合成的并行处理与文本缓冲策略；在前端采用 1.5 秒音频预缓冲消除卡顿；通过 AudioBuffer 将小片段合并为 8KB 块批量发送；构建包含手动按钮和 VAD 自动检测的多层级打断机制。

（5）**测试与评估**：编写覆盖 RAG 评估、BM25、查询改写等模块的 16 个单元测试用例；开发 WebSocket 端到端自动化测试客户端；构建 45 条覆盖多个维修子领域的测试集，基于 Hit Rate、MRR、nDCG 三项指标对各优化策略进行定量对比。

## 1.4 本文组织结构

本文共分为七章，各章内容安排如下：

第一章 引言：阐述研究背景、意义及国内外研究现状，概述本文主要工作。

第二章 相关技术：介绍 RAG、LLM、STT/TTS、WebSocket、asyncio 和 Web Audio API 等关键技术。

第三章 系统需求分析与设计：进行需求分析，设计四层总体架构、端到端流式数据流，以及 RAG 检索、语音识别、语言模型推理、语音合成和会话编排与服务接入五个核心模块。

第四章 系统实现：对应第三章的模块划分，说明文档预处理、索引构建、各核心模块实现以及会话编排与服务接入机制的具体落地方式。

第五章 系统优化：阐述 RAG 检索精度和流式交互体验两维度的优化工作。

第六章 系统测试与结果分析：展示单元测试、端到端测试和 RAG 定量对比实验结果。

第七章 结论与展望：总结研究成果，分析不足并展望未来改进方向。

## 参考文献（第一章引用）

[1] Lewis P, Perez E, Piktus A, et al. Retrieval-augmented generation for knowledge-intensive NLP tasks[C]//Advances in Neural Information Processing Systems, 2020, 33: 9459-9474.

[2] Karpukhin V, Oguz B, Min S, et al. Dense passage retrieval for open-domain question answering[C]//Proceedings of the 2020 Conference on Empirical Methods in Natural Language Processing (EMNLP), 2020: 6769-6781.

[3] Nogueira R, Cho K. Passage re-ranking with BERT[J]. arXiv preprint arXiv:1901.04085, 2019.

[4] Glass M, Rossiello G, Chowdhury M F M, et al. Re2G: Retrieve, rerank, generate[C]//Proceedings of the 2022 Conference of the North American Chapter of the Association for Computational Linguistics (NAACL), 2022: 2701-2715.

[5] Huang L, Yu W, Ma W, et al. A survey on hallucination in large language models: Principles, taxonomy, challenges, and open questions[J]. arXiv preprint arXiv:2311.05232, 2023.

[6] Xiong G, Ji J, Wang L, et al. KG-RAG: Bridging the gap between knowledge and creativity[J]. arXiv preprint arXiv:2405.12035, 2024.

[7] Gao Z, Zhang S, McLoughlin I, et al. Paraformer: Fast and accurate parallel transformer for non-autoregressive end-to-end speech recognition[C]//Proceedings of Interspeech, 2022: 2063-2067.

[8] Du Z, Chen S, Ma Z, et al. CosyVoice: A scalable multilingual zero-shot text-to-speech synthesizer based on supervised semantic tokens[J]. arXiv preprint arXiv:2407.05407, 2024.

[9] Young S, Gasic M, Thomson B, et al. POMDP-based statistical spoken dialog systems: A review[J]. Proceedings of the IEEE, 2013, 101(5): 1160-1179.

[10] Reddy S, Reddy V, Borah S. A novel approach for medical question answering using retrieval-augmented generation[C]//International Conference on Artificial Intelligence, 2024.

[11] Yang C, Chen Z, Li X. SpeechRAG: Retrieval-augmented generation for spoken question answering[J]. arXiv preprint arXiv:2501.00031, 2024.
