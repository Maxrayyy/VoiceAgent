"""元数据提取与过滤单元测试"""
import pytest

from src.rag.document_loader import load_txt_with_metadata


class TestMetadataExtraction:
    """测试从 full_text.txt 格式提取元数据"""

    def test_chapter_extraction(self):
        """章节标记应正确提取"""
        text = (
            "===== 第 9 页 =====\n"
            "第1章飞机客舱\n\n"
            "1.1飞机客舱的基本结构\n\n"
            "飞机客舱，是容纳乘客，并为乘客提供必要生活服务的区域。"
            "现代客机的机身较大，客舱内采用了越来越高的舒适标准。"
            "一般而言，民用客机的客舱前起前客舱隔墙，后至后密封舱壁。"
        )
        docs = load_txt_with_metadata(text, source="test.txt")
        assert len(docs) >= 1
        assert docs[0]["chapter"] == "第1章飞机客舱"
        assert docs[0]["section"] == "1.1"
        assert docs[0]["page"] == 9

    def test_chapter_inherits_across_chunks(self):
        """后续 chunk 应继承最近的章节信息"""
        text = (
            "===== 第 17 页 =====\n"
            "第2章飞机座椅的结构与维修\n\n"
            "2.1飞机座椅的结构、拆装和排故\n\n"
            "在对客舱进行检修时，经常需拆卸、检查、维修并安装座椅。"
            "安装后的座椅还需用专门的设备对其进行测试。"
            "如测试椅背在受到一定垂直冲击力时，是否能安全地倒折下来。"
            "\n\n"
            "2.1.1飞机座椅的一般结构\n\n"
            "飞机座椅一般可分解为扶手组件、靠背组件、小桌板组件、椅身组件。"
            "安全带组件、靠背倾斜调节装置、海绵垫、纺织品外罩套和杂物袋等。"
            "早期的座椅结构比较简单，但其发展的趋势是结构越来越复杂。"
        )
        docs = load_txt_with_metadata(text, source="test.txt")
        assert len(docs) >= 1
        for doc in docs:
            assert doc["chapter"] == "第2章飞机座椅的结构与维修"
        last = docs[-1]
        assert last["section"] == "2.1.1"

    def test_page_updates(self):
        """页码应在遇到新页标记时更新"""
        text = (
            "===== 第 9 页 =====\n"
            "第1章飞机客舱\n\n"
            "这是第9页的内容，需要足够长以便形成一个独立的chunk。"
            "飞机客舱是容纳乘客的区域，为乘客提供必要的生活服务和舒适环境。"
            "现代客机的机身较大，客舱内采用了越来越高的舒适标准和人性化设计理念。"
            "一般而言，民用客机的客舱前起前客舱隔墙，后至后密封舱壁，形成一个完整的密闭空间。"
            "客舱内部空间宽敞舒适，座椅排列整齐有序，通道宽度完全符合国际民航安全标准的规定。"
            "头顶上方设有行李舱架，用于存放旅客的随身行李箱包和各种便携物品设备。"
            "客舱还配备了先进的LED照明系统、自动空调系统和个人娱乐系统等现代化设施设备。"
            "乘务员服务区域位于前舱和后舱的适当位置，配有厨房和工作台，方便为旅客提供及时周到的优质服务。"
            "紧急出口和各种应急安全设备布置在客舱的关键战略位置，充分确保旅客在紧急情况下的生命安全。"
            "客舱地板下方还设有大容量货舱，用于装载旅客托运的各类行李物品和航空货物。"
            "现代客舱还特别注重降噪设计，通过隔音材料和结构优化，为旅客提供更加安静舒适的飞行环境体验。"
            "\n\n"
            "===== 第 10 页 =====\n"
            "这是第10页的内容，也需要足够长以便能单独成为一个完全独立的文档分块。"
            "现代客机机身段是由隔框、大梁、长桁和蒙皮等多种金属构件组成的复杂承力结构体系。"
            "这种结构在航空工程中称为半硬壳式结构，在此基本结构框架基础上还开设有舷窗和各种功能性舱门。"
            "隔框是机身的主要横向支撑骨架构件，其重要作用是保持机身的圆形截面形状不发生变形和失稳。"
            "长桁沿着机身纵向方向连续布置，与外部蒙皮蒙皮板共同协调工作，一起承受飞行中的弯曲载荷和扭转载荷。"
            "大梁主要战略性布置在机身的关键主要承力部位和重要结构连接位置，专门用于加强机身的整体结构强度和刚度。"
            "蒙皮不仅形成光滑的气密外壳为客舱提供增压密封功能，还直接参与承载机身在飞行中承受的各种复杂气动力载荷分布。"
            "舷窗和舱门的矩形开口显著削弱了原有蒙皮的连续性和结构强度，因此这些薄弱区域需要进行特殊的工程加强处理措施。"
            "机身结构的工程设计必须同时全面满足强度、刚度、整体稳定性和长期耐久性等多方面严格的适航技术要求规范。"
        )
        docs = load_txt_with_metadata(text, source="test.txt")
        pages = [d["page"] for d in docs]
        assert 9 in pages
        assert 10 in pages

    def test_no_metadata_markers(self):
        """没有元数据标记时使用默认值"""
        text = (
            "这是一段没有任何章节或页码标记的纯文本内容。"
            "需要确保它足够长以形成一个独立的chunk片段。"
            "系统应当为其赋予默认的元数据值而不是报错。"
        )
        docs = load_txt_with_metadata(text, source="test.txt")
        assert len(docs) >= 1
        assert docs[0]["chapter"] == ""
        assert docs[0]["section"] == ""
        assert docs[0]["page"] == 0

    def test_metadata_fields_present(self):
        """每个 chunk 都必须包含 chapter、section、page 字段"""
        text = (
            "===== 第 20 页 =====\n"
            "第3章客舱系统\n\n"
            "3.1照明系统\n\n"
            "客舱照明系统为旅客和乘务员提供必要的照明环境。"
            "系统由多种灯具组成，包括天花板灯、阅读灯和应急照明灯。"
            "照明控制通过驾驶舱面板和乘务员操作面板进行调节。"
        )
        docs = load_txt_with_metadata(text, source="test.txt")
        for doc in docs:
            assert "chapter" in doc
            assert "section" in doc
            assert "page" in doc
            assert "content" in doc
            assert "source" in doc


from src.rag.retriever import DocumentStore


class TestMetadataFiltering:
    """测试检索时的元数据过滤"""

    def test_match_filters_chapter(self):
        """按章节过滤"""
        store = DocumentStore()
        doc = {"content": "test", "source": "t.txt", "chapter": "第2章飞机座椅", "section": "2.1", "page": 17}
        assert store._match_filters(doc, {"chapter": "第2章飞机座椅"}) is True
        assert store._match_filters(doc, {"chapter": "第1章飞机客舱"}) is False

    def test_match_filters_page_range(self):
        """按页码范围过滤"""
        store = DocumentStore()
        doc = {"content": "test", "source": "t.txt", "chapter": "", "section": "", "page": 25}
        assert store._match_filters(doc, {"page_min": 20, "page_max": 30}) is True
        assert store._match_filters(doc, {"page_min": 30, "page_max": 40}) is False

    def test_match_filters_empty(self):
        """空过滤条件匹配所有"""
        store = DocumentStore()
        doc = {"content": "test", "source": "t.txt"}
        assert store._match_filters(doc, {}) is True

    def test_match_filters_partial_match(self):
        """chapter 支持子字符串匹配"""
        store = DocumentStore()
        doc = {"content": "test", "source": "t.txt", "chapter": "第2章飞机座椅的结构与维修", "section": "", "page": 0}
        assert store._match_filters(doc, {"chapter": "座椅"}) is True
        assert store._match_filters(doc, {"chapter": "客舱"}) is False
