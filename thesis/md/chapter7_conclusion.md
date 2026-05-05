# 第七章 总结与展望

## 7.1 工作总结

本文面向航空维修领域的智能语音问答需求，设计并实现了一个基于检索增强生成技术的端到端流式语音问答项目。围绕知识检索、语音交互和会话编排三个层面，本文完成的主要工作与成果如下。

（1）**系统架构**。本文构建了基于 FastAPI 与 WebSocket 的端到端流式问答架构，并将检索、识别、生成、合成和会话编排统一到同一处理链路中。针对第三方语音 SDK 存在阻塞调用与回调线程的特点，项目采用协程与线程混合调度方式，保证了整条链路在实时性与稳定性之间的平衡。

（2）**RAG 知识库构建**。采用 PaddleX 版面分析 + PaddleOCR 从 5 份飞机维修手册 PDF 提取高质量文本，基于自然段落实现 300-800 字的智能切分，自动抽取章节、小节与页码元数据，共构建 1478 个文档片段的 FAISS 向量索引与 BM25 稀疏索引双索引体系。

（3）**RAG 检索优化**。实现混合检索（BM25 + FAISS + RRF）、交叉编码器重排序、查询改写、上下文增强切分、航空术语词典与元数据过滤六项优化，在 45 条测试查询上 Hit Rate@5 由 73.33% 提升至 95.56%，MRR@5 由 0.5781 提升至 0.9444，nDCG@5 由 0.6140 提升至 0.9459。

（4）**流式交互优化**。本文通过并行处理、文本缓冲、音频预缓冲、音频批量发送、多层级打断与静音容忍等优化手段，显著改善了语音交互链路的等待体验，使端到端延迟由约 5.6 秒降至约 1.6 秒，降幅约为 71%。

（5）**测试与前端**。建立 16 个单元测试、WebSocket 端到端测试与 RAG 性能评估的测试体系，并实现航空仪表盘风格 Web 前端，支持语音/文本双输入、波形可视化与 RAG 来源展示。

## 7.2 不足分析

（1）**知识库规模仍有扩展空间**。当前包含 5 份核心维修资料（1478 个文档片段），更大规模多机型与跨厂商场景下的性能有待进一步验证。
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

在毕业设计的完成过程中，感谢指导教师的悉心指导和帮助，为本课题的选题方向和技术方案提供了宝贵的建议。同时感谢阿里云 DashScope 平台提供的 AI 模型服务和 PaddlePaddle 社区提供的开源工具，为本项目的实现提供了有力的技术支撑。最后，感谢各位老师和同学在学习和生活中给予的帮助和支持。
