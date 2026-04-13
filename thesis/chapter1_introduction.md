# 第一章 引言

## 1.1 研究背景与意义

随着人工智能技术的飞速发展，语音交互作为最自然的人机交互方式之一，正在深刻改变各行业的工作模式。在航空维修领域，维修技术人员在执行飞机检修任务时，通常需要频繁查阅维修手册、技术通报等大量技术文档。传统的人工查阅方式不仅耗时费力，而且在高噪声、手持工具等实际工作场景中极为不便。因此，构建一个能够通过语音进行自然对话、快速精准地从专业知识库中检索并回答技术问题的智能助手系统，对于提升航空维修效率和保障飞行安全具有重要的现实意义。

近年来，以 ChatGPT 为代表的大语言模型（Large Language Model, LLM）展现出了强大的自然语言理解和生成能力，为构建智能问答系统提供了新的技术范式。然而，大语言模型在面对专业领域知识时存在"幻觉"（Hallucination）问题，即模型可能生成看似合理但实际不正确的内容。在航空维修这一安全关键领域，错误的技术指导可能导致严重的安全事故，因此单纯依赖大语言模型的生成能力是不可接受的。

检索增强生成（Retrieval-Augmented Generation, RAG）技术通过将外部知识库与大语言模型相结合，在生成回答前先从权威文档中检索相关内容作为参考依据，有效缓解了模型幻觉问题，使生成的回答更加准确可靠。RAG 技术特别适用于航空维修这类对信息准确性要求极高的专业场景。

与此同时，实时语音交互技术也面临着延迟挑战。传统的语音问答系统通常采用串行处理方式：先完成语音识别，再进行文本处理，最后进行语音合成，整个流程的累积延迟往往超过数秒，严重影响用户体验。流式处理技术的引入使得各模块可以并行工作——语音识别边听边转写、大模型边生成边合成语音，从而将端到端延迟大幅降低。

基于上述背景，本文设计并实现了一个面向航空维修领域的知识增强语音问答 Agent 系统。该系统集成了语音识别（STT）、检索增强生成（RAG）、大语言模型推理（LLM）和语音合成（TTS）四大核心模块，采用端到端流式架构和混合检索优化策略，旨在为维修技术人员提供一个高效、准确、自然的语音交互式技术咨询工具。

## 1.2 国内外研究现状

### 1.2.1 检索增强生成技术研究现状

检索增强生成（RAG）的概念最早由 Lewis 等人于 2020 年提出[1]，其核心思想是在大语言模型生成回答之前，先从外部知识库中检索相关文档片段，将检索结果作为上下文信息注入到模型的输入中，从而引导模型基于事实信息生成回答。

在检索环节，密集向量检索（Dense Passage Retrieval, DPR）技术[2]利用预训练语言模型将文本编码为稠密向量，通过向量相似度计算实现语义级别的检索，相比传统的稀疏检索方法（如 BM25）在语义理解方面有显著优势。然而，稠密检索在处理专业术语和精确匹配场景时可能不如稀疏检索有效，因此近年来混合检索（Hybrid Search）方法受到广泛关注，即同时利用稠密检索和稀疏检索的互补优势，通过融合算法（如倒数排名融合 RRF）综合两者的检索结果。

在检索结果优化方面，交叉编码器重排序（Cross-Encoder Reranking）技术[3]通过对查询和文档进行联合编码和精细评分，能够在初步检索结果的基础上进一步提升排序质量。Glass 等人的研究表明[4]，重排序机制可以显著降低检索噪声，提高最终生成答案的准确性。

针对大语言模型的幻觉问题，Huang 等人[5]系统分析了幻觉产生的原因和缓解策略，指出 RAG 是目前最有效的幻觉缓解方法之一。此外，Xiong 等人[6]提出了基于图结构知识增强的 RAG 方法，进一步提升了知识检索的准确性。

### 1.2.2 语音交互技术研究现状

语音识别（Automatic Speech Recognition, ASR）技术经过多年发展，已从传统的基于隐马尔可夫模型（HMM）的方法演进到基于深度学习的端到端模型。FunASR[7]等开源框架实现了高精度的中文语音识别，支持实时流式转写。商业化语音识别服务如阿里云智能语音交互（NLS）则提供了更加稳定的生产级 API 接口，支持实时音频流的边说边识别，延迟可控制在毫秒级。

语音合成（Text-to-Speech, TTS）领域同样取得了长足进步。CosyVoice[8]等新一代语音合成模型能够生成自然流畅、音色丰富的语音，并支持流式合成——即无需等待完整文本即可开始输出音频，这对于降低语音问答系统的整体延迟至关重要。

在语音对话系统方面，传统的任务型对话系统通常采用 NLU-DM-NLG 流水线架构[9]，而现代系统越来越多地引入大语言模型作为对话引擎，通过 RAG 技术提供领域知识支撑。Reddy 等人[10]探索了将 RAG 应用于医疗问答场景，Yang 等人[11]则研究了 RAG 在语音场景中的扩展应用，验证了 RAG 与语音交互结合的可行性和有效性。

### 1.2.3 流式交互优化研究现状

端到端延迟是语音交互系统用户体验的关键指标。研究表明，当系统响应延迟超过 2 秒时，用户会明显感受到等待，超过 5 秒则会显著降低用户满意度。因此，如何在保证回答质量的前提下尽可能降低响应延迟，是语音问答系统面临的重要技术挑战。

流式处理（Streaming Processing）是降低延迟的核心技术手段。通过将传统的"等待完成后处理"模式转变为"边接收边处理"模式，各模块之间的等待时间可以被有效消除。在 WebSocket 全双工通信协议的支持下，前端和后端可以同时进行双向数据传输，为实时语音交互提供了良好的基础设施支持。

## 1.3 本文主要工作

本文围绕面向航空维修领域的知识增强语音问答 Agent 系统，开展了以下主要工作：

（1）**系统架构设计**：设计了一套基于 FastAPI + WebSocket 的端到端流式语音问答架构，集成 STT、RAG、LLM、TTS 四大模块，通过异步协程与多线程混合调度实现全链路流式处理，将用户从说完话到听到回答的延迟控制在 1-2 秒。

（2）**RAG 检索系统构建**：构建了面向航空维修手册的 RAG 知识库，实现了文档智能切分、向量化索引等基础功能，并集成了稠密检索（FAISS）、稀疏检索（BM25）和交叉编码器重排序三种检索技术。

（3）**RAG 检索优化**：提出并实现了多项检索优化策略，包括混合检索与 RRF 融合、交叉编码器重排序、查询改写（口语化规范化和多轮对话指代消解）、上下文增强切分（Contextual Chunking）和航空术语自定义词典等，使检索命中率从 86.67% 提升至 97.78%。

（4）**流式交互优化**：实现了 STT 实时流式识别、LLM 流式生成与 TTS 流式合成的并行处理，设计了文本缓冲策略和音频预缓冲机制，并实现了多层级的语音打断功能，显著提升了交互流畅度。

（5）**系统测试与评估**：建立了完整的测试体系，包括单元测试、端到端测试和 RAG 检索性能评估，使用 Hit Rate、MRR、nDCG 三项标准信息检索指标对不同检索策略进行了定量对比实验。

## 1.4 本文组织结构

本文共分为七章，各章内容安排如下：

**第一章 引言**：介绍课题的研究背景和意义，综述国内外相关技术的研究现状，概述本文的主要工作和论文的组织结构。

**第二章 相关技术**：介绍本系统涉及的关键技术，包括检索增强生成（RAG）、大语言模型、语音识别、语音合成、WebSocket 通信协议、向量检索等技术的基本原理。

**第三章 系统需求分析与设计**：从功能需求和非功能需求两方面进行需求分析，设计系统的总体架构和各功能模块，给出关键的接口设计和数据流设计。

**第四章 系统实现**：详细描述各模块的具体实现过程，包括文档预处理与索引构建、RAG 检索流水线、流式语音交互、前端界面等关键功能的实现细节。

**第五章 系统优化**：阐述在 RAG 检索和流式交互两个维度进行的优化工作，包括混合检索、重排序、查询改写、上下文增强切分、流式并行处理、语音打断等优化策略。

**第六章 系统测试与结果分析**：介绍系统的测试方案和测试环境，展示单元测试、端到端测试和 RAG 检索评估的实验结果，并对结果进行分析讨论。

**第七章 结论与展望**：总结本文的主要工作和成果，分析系统的不足之处，展望未来的改进方向。

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
