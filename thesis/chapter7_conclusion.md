# 第七章 结论与展望

## 7.1 工作总结

本文围绕航空维修领域的智能语音问答需求，设计并实现了一个基于检索增强生成（RAG）技术的端到端流式语音问答 Agent 系统。系统集成了语音识别（STT）、检索增强生成（RAG）、大语言模型推理（LLM）和语音合成（TTS）四大核心模块，通过异步协程与多线程混合调度实现了全链路流式处理。本文的主要工作和成果总结如下：

（1）**构建了完整的系统架构**。设计并实现了基于 FastAPI + WebSocket 的端到端流式语音问答架构，采用 asyncio 协程与 daemon 线程混合调度模型，解决了异步事件循环与第三方阻塞 SDK 的协作问题。通过 `call_soon_threadsafe` 和 `run_coroutine_threadsafe` 机制实现了安全的跨线程通信，为系统的高并发和低延迟提供了基础保障。

（2）**构建了面向航空维修的 RAG 知识库**。采用 PaddleX 版面分析加 PaddleOCR 文字识别方案从维修手册 PDF 中提取高质量文本，实现了基于自然段落的智能切分策略（300-800 字），并自动提取章节、小节和页码元数据。构建了 FAISS 向量索引和 BM25 稀疏索引双索引体系。

（3）**实现了多层次的 RAG 检索优化**。提出并实现了混合检索（BM25 + FAISS + RRF 融合）、交叉编码器重排序、查询改写（口语化规范化和指代消解）、上下文增强切分和航空术语自定义词典五项优化策略。实验结果表明，经过优化后系统的 Hit Rate@5 从 84.44% 提升至 97.78%，MRR@5 从 0.6626 提升至 0.9667，nDCG@5 从 0.7071 提升至 0.9678，各项指标均达到较高水平。

（4）**实现了端到端流式交互优化**。通过 STT 实时流式识别、LLM 流式生成与 TTS 流式合成的并行处理，配合文本缓冲策略和音频预缓冲机制，将端到端延迟从约 5.6 秒降低至约 1.6 秒，延迟降低约 71%。同时实现了多层级的语音打断功能（手动打断和 VAD 语音打断），提升了交互的自然度。

（5）**建立了完善的测试与评估体系**。设计了包含单元测试（16 个用例）、端到端 WebSocket 测试和 RAG 检索性能评估的完整测试方案。使用 LLM 自动生成了覆盖多个飞机维修子领域的 45 条测试查询作为评估数据集，采用 Hit Rate、MRR、nDCG 三项标准信息检索指标进行定量评估。

（6）**实现了可用的 Web 前端界面**。基于原生 HTML/CSS/JavaScript 和 Web Audio API 实现了航空仪表盘风格的交互界面，支持语音输入和文本输入两种模式、持续监听和按住说话两种录音模式、实时音频波形可视化、RAG 来源信息展示等功能。

## 7.2 不足分析

尽管本系统在功能实现和性能优化方面取得了一定的成果，但仍存在以下不足：

（1）**知识库规模有限**。当前知识库仅包含单本飞机维修手册的内容，数据量约 432KB。在实际应用中，航空维修涉及多种机型、多本手册和大量技术通报，知识库规模将远超当前水平。系统在大规模知识库场景下的检索性能和效率有待验证。

（2）**评估数据集规模较小**。当前评估数据集仅包含 45 条测试查询，虽然覆盖了多个飞机维修子领域，但规模仍然有限，评估结果的统计显著性有待提升。此外，评估数据集是通过 LLM 自动生成的，可能存在与真实用户查询分布不一致的问题。

（3）**缺少端到端的自动化回归测试**。当前的端到端测试依赖手动运行测试脚本和人工检查结果，缺少自动化的回归测试流程。在系统迭代过程中，难以快速发现和定位引入的问题。

（4）**对云服务的依赖**。系统的 STT、LLM、TTS、Embedding 和 Rerank 等核心功能均依赖阿里云的云端 API 服务。在网络不稳定或服务不可用时，系统将无法正常工作。同时，API 调用成本也是实际部署时需要考虑的因素。

（5）**缺少用户体验评估**。当前的评估主要集中在 RAG 检索性能的客观指标上，缺少对真实用户使用体验的主观评估（如用户满意度、任务完成率等）。

## 7.3 未来展望

针对上述不足，未来的改进方向包括：

（1）**知识库扩展与管理**。支持多文档、多机型知识库的构建和管理，实现增量索引更新（无需每次全量重建），探索向量数据库（如 Milvus、Qdrant 等）替代 FAISS 以支持更大规模的数据和更灵活的索引管理。

（2）**检索策略进一步优化**。探索层次化检索（先定位章节再在章节内检索）、Self-RAG（模型自主判断是否需要检索以及检索结果的可靠性）等高级检索策略。同时可以对 Embedding 模型进行领域微调，提升航空维修领域的语义理解能力。

（3）**多模态支持**。扩展系统以支持图片（如维修示意图、故障照片）的输入和输出，构建多模态 RAG 系统，更好地服务于实际维修场景。

（4）**离线能力**。研究本地部署的轻量级模型（如 SenseVoice 本地 STT、CosyVoice 本地 TTS、Qwen 本地推理等），使系统在无网络环境下也能提供基本的问答功能，满足部分维修场景对离线能力的需求。

（5）**用户体验优化**。设计和实施用户体验评估实验，收集真实维修人员的使用反馈，持续优化交互流程和回答质量。同时可以引入个性化功能（如记忆用户常查的机型和系统），进一步提升使用体验。

（6）**安全性增强**。在航空维修这一安全关键领域，可以引入回答置信度评估机制，对低置信度的回答进行标注和提醒，并建立专家审核机制，确保系统输出的安全性和可靠性。

## 参考文献

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

[12] Robertson S, Zaragoza H. The probabilistic relevance framework: BM25 and beyond[J]. Foundations and Trends in Information Retrieval, 2009, 3(4): 333-389.

[13] Johnson J, Douze M, Jégou H. Billion-scale similarity search with GPUs[J]. IEEE Transactions on Big Data, 2019, 7(3): 535-547.

## 致谢

在毕业设计的完成过程中，感谢指导教师的悉心指导和帮助，为本课题的选题方向和技术方案提供了宝贵的建议。同时感谢阿里云 DashScope 平台提供的 AI 模型服务和 PaddlePaddle 社区提供的开源工具，为本系统的实现提供了有力的技术支撑。最后，感谢各位老师和同学在学习和生活中给予的帮助和支持。
