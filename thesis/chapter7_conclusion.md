# 第七章 结论与展望

## 7.1 工作总结

本文面向航空维修领域的智能语音问答需求，设计并实现了一个基于检索增强生成（RAG）技术的端到端流式语音问答 Agent 系统，集成 STT、RAG、LLM、TTS 四大模块。主要工作与成果如下：

（1）**系统架构**。基于 FastAPI + WebSocket 搭建端到端流式问答架构，采用 asyncio 协程与 daemon 线程混合调度，通过 `call_soon_threadsafe` 等机制实现跨线程安全通信，解决异步事件循环与第三方阻塞 SDK 的协作问题。

（2）**RAG 知识库构建**。采用 PaddleX 版面分析 + PaddleOCR 从维修手册 PDF 提取高质量文本，基于自然段落实现 300-800 字的智能切分，自动抽取章节、小节与页码元数据，构建 FAISS 向量索引与 BM25 稀疏索引的双索引体系。

（3）**RAG 检索优化**。实现混合检索（BM25 + FAISS + RRF）、交叉编码器重排序、查询改写、上下文增强切分、航空术语词典与元数据过滤六项优化，Hit Rate@5 由 84.44% 提升至 97.78%，MRR@5 由 0.6626 提升至 0.9667，nDCG@5 由 0.7071 提升至 0.9678。

（4）**流式交互优化**。通过 STT、LLM、TTS 并行调度，配合文本缓冲、音频预缓冲、AudioBuffer 批量发送、多层级打断与 STT 静音容忍等优化，端到端延迟由约 5.6 秒降至约 1.6 秒，降低约 71%。

（5）**测试与前端**。建立 16 个单元测试、WebSocket 端到端测试与 RAG 性能评估的测试体系，并实现航空仪表盘风格 Web 前端，支持语音/文本双输入、波形可视化与 RAG 来源展示。

## 7.2 不足分析

（1）**知识库规模有限**。当前仅包含单本维修手册（约 432 KB），大规模多机型场景下的性能有待验证。
（2）**评估数据集较小**。45 条由 LLM 自动生成的查询在统计显著性和分布真实性上仍有不足。
（3）**缺少自动化回归测试**。端到端测试仍依赖人工执行，难以在迭代中快速发现回归问题。
（4）**对云服务依赖较强**。STT、LLM、TTS、Embedding 和 Rerank 均依赖云端 API，网络异常或成本控制是实际部署的约束。

## 7.3 未来展望

（1）**知识库扩展与管理**。支持多手册、多机型，实现增量索引更新，并探索 Milvus、Qdrant 等向量数据库以承载更大规模数据。
（2）**检索策略进阶**。引入层次化检索与 Self-RAG，并对 Embedding 模型进行领域微调，提升航空语料的语义理解能力。
（3）**多模态与离线能力**。扩展图片输入输出构建多模态 RAG，并研究 SenseVoice、CosyVoice、Qwen 等本地轻量模型以支持离线场景。
（4）**安全性与用户体验**。引入回答置信度评估与专家审核机制，同时设计用户体验评估实验收集真实维修人员反馈，持续迭代交互与回答质量。

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
