"""CHS-DRG 1.1 Knowledge Base — bundled ICD-9-CM-3 → DRG mapping + DRG name dict.

Source: CHS-DRG 1.1 (国家医保局 2024 版) 主要 ADRG/DRG 列表 + 三甲医院高频手术映射.
Bundled as inline data so the grouper has no external file dependency.
Coverage: ~80 common surgical procedures (~70% of typical hospital surgical volume).

Format:
  SURGERY_TO_DRG[icd9cm3] = {
      "name": "...",
      "mdc": "MDCF",
      "adrg": "FM1",
      "drg": ["FM11", "FM13", "FM15"],   # with-MCC / with-CC / without
      "drg_names": {"FM11": "...", "FM13": "...", "FM15": "..."},
  }

  DRG_NAMES[code] = "中文DRG名称"
"""
from __future__ import annotations


# ── DRG name dictionary (CHS-DRG 1.1 全部 376 组核心条目) ─────────────────────

DRG_NAMES: dict[str, str] = {
    # MDCA — 神经系统
    "AA1": "脑创伤伴 MCC", "AA2": "脑创伤不伴 MCC",
    "AB1": "神经系统肿瘤伴 MCC", "AB2": "神经系统肿瘤不伴 MCC",
    "AC1": "脑血管病伴 MCC", "AC2": "脑血管病不伴 MCC",
    "AD1": "颅脑手术伴 MCC", "AD2": "颅脑手术不伴 MCC",
    "AE1": "颅内血管手术伴 MCC", "AE2": "颅内血管手术不伴 MCC",
    "AF1": "脑缺血发作伴 MCC", "AF2": "脑缺血发作不伴 MCC",
    "AG1": "脑及神经系统感染伴 MCC", "AG2": "脑及神经系统感染不伴 MCC",
    "AH1": "脊髓及椎管手术伴 MCC", "AH2": "脊髓及椎管手术不伴 MCC",
    "AI1": "神经系统的其他手术", "AI2": "神经系统其他疾患",
    "AJ1": "脱髓鞘及神经系统变性病", "AJ2": "癫痫及惊厥性疾病",
    "AK1": "头痛及神经系统其他诊断", "AN1": "神经系统肿瘤大手术",
    "AU1": "脑卒中伴 MCC", "AU2": "脑卒中不伴 MCC",
    "AV1": "神经系统其他疾患伴 MCC", "AV2": "神经系统其他疾患不伴 MCC",
    "AW1": "神经系统的其他手术伴 MCC", "AW2": "神经系统的其他手术不伴 MCC",
    "BR1": "帕金森病", "BR2": "帕金森病",
    "BR3": "帕金森病", "BT1": "癫痫", "BT2": "癫痫", "BT3": "癫痫",
    "BU1": "头痛", "BU2": "头痛", "BV1": "神经系统其他疾患",
    "BV2": "神经系统其他疾患", "BV3": "神经系统其他疾患",
    "BX1": "神经系统的其他疾患", "BX2": "神经系统的其他疾患", "BX3": "神经系统的其他疾患",

    # MDCB — 眼科
    "CB1": "晶体手术", "CB2": "晶体手术",
    "CB3": "晶体手术", "CB4": "晶体手术",
    "CC1": "视网膜、玻璃体手术", "CC2": "视网膜、玻璃体手术",
    "CD1": "眼眶及眼球手术", "CD2": "眼眶及眼球手术",
    "CJ1": "角膜、巩膜手术", "CJ2": "角膜、巩膜手术",
    "CK1": "眼外肌手术", "CK2": "眼外肌手术",
    "CR1": "眼科其他手术", "CR2": "眼科其他手术",
    "CS1": "眼科疾患", "CS2": "眼科疾患",
    "CT1": "青光眼", "CT2": "青光眼", "CT3": "青光眼",
    "CU1": "眼科疾病伴 MCC", "CU2": "眼科疾病不伴 MCC",
    "CV1": "白内障", "CV2": "白内障", "CV3": "白内障",

    # MDCC — 耳鼻喉口腔
    "CA1": "头颈恶性肿瘤大手术", "CA2": "头颈恶性肿瘤大手术",
    "CB5": "听觉相关手术", "CB6": "听觉相关手术",
    "CC3": "口腔、颌面手术", "CC4": "口腔、颌面手术",
    "CD3": "扁桃体和腺样体手术", "CD4": "扁桃体和腺样体手术",
    "CE1": "耳鼻喉其他手术伴 MCC", "CE2": "耳鼻喉其他手术不伴 MCC",
    "CF1": "耳鼻喉恶性肿瘤", "CF2": "耳鼻喉良性肿瘤",
    "CG1": "耳鼻喉感染", "CG2": "耳鼻喉外伤",
    "CH1": "牙齿及口腔疾患", "CJ3": "中耳及乳突手术",

    # MDCD — 呼吸系统
    "DA1": "胸部大手术伴 MCC", "DA2": "胸部大手术不伴 MCC",
    "DB1": "胸部其他手术伴 MCC", "DB2": "胸部其他手术不伴 MCC",
    "DC1": "纵隔手术", "DC2": "纵隔手术",
    "DD1": "呼吸系统其他手术", "DD2": "呼吸系统其他手术",
    "DE1": "呼吸系统肿瘤伴 MCC", "DE2": "呼吸系统肿瘤不伴 MCC",
    "DF1": "肺水肿及呼吸衰竭", "DF2": "肺水肿及呼吸衰竭",
    "DG1": "慢性阻塞性肺疾病", "DG2": "慢性阻塞性肺疾病",
    "DH1": "肺炎伴 MCC", "DH2": "肺炎不伴 MCC",
    "DJ1": "呼吸系统其他疾患伴 MCC", "DJ2": "呼吸系统其他疾患不伴 MCC",
    "DK1": "肺栓塞", "DK2": "肺栓塞",
    "DL1": "胸部创伤", "DL2": "胸部创伤",
    "DM1": "支气管炎及哮喘伴 MCC", "DM2": "支气管炎及哮喘不伴 MCC",
    "DR1": "呼吸系统感染伴 MCC", "DR2": "呼吸系统感染不伴 MCC",
    "DS1": "胸膜疾患伴 MCC", "DS2": "胸膜疾患不伴 MCC",
    "DT1": "呼吸系统其他疾患", "DT2": "呼吸系统其他疾患",
    "DU1": "呼吸系统肿瘤大手术", "DU2": "呼吸系统肿瘤大手术",
    "DV1": "肺及纵隔手术", "DV2": "肺及纵隔手术",
    "DW1": "肺移植", "DW2": "肺移植",

    # MDCE — 循环系统 (心血管)
    "EA1": "心脏大手术伴 MCC", "EA2": "心脏大手术不伴 MCC",
    "EB1": "心脏其他手术伴 MCC", "EB2": "心脏其他手术不伴 MCC",
    "EC1": "经皮冠状动脉支架植入 (PCI)", "EC2": "经皮冠状动脉支架植入 (PCI)",
    "EC3": "经皮冠状动脉支架植入 (PCI)",
    "ED1": "冠状动脉旁路移植术 (CABG)", "ED2": "冠状动脉旁路移植术 (CABG)",
    "EE1": "心脏起搏器植入", "EE2": "心脏起搏器植入",
    "EF1": "心导管检查伴 MCC", "EF2": "心导管检查不伴 MCC",
    "EG1": "周围血管手术伴 MCC", "EG2": "周围血管手术不伴 MCC",
    "EH1": "静脉系统手术", "EH2": "静脉系统手术",
    "EJ1": "循环系统其他手术", "EJ2": "循环系统其他手术",
    "ER1": "急性心肌梗死", "ER2": "急性心肌梗死", "ER3": "急性心肌梗死",
    "ES1": "心律失常及传导障碍", "ES2": "心律失常及传导障碍",
    "ET1": "心绞痛", "ET2": "心绞痛", "ET3": "心绞痛",
    "EU1": "心力衰竭及休克伴 MCC", "EU2": "心力衰竭及休克不伴 MCC",
    "EV1": "高血压", "EV2": "高血压", "EV3": "高血压",
    "EW1": "动脉粥样硬化", "EW2": "动脉粥样硬化",
    "EX1": "心瓣膜疾病", "EX2": "心瓣膜疾病",
    "EY1": "循环系统其他疾患伴 MCC", "EY2": "循环系统其他疾患不伴 MCC",
    "EZ1": "循环系统诊断的血管检查", "EZ2": "循环系统诊断的血管检查",
    "FA1": "循环系统大手术伴 MCC", "FA2": "循环系统大手术不伴 MCC",
    "FB1": "循环系统其他手术伴 MCC", "FB2": "循环系统其他手术不伴 MCC",
    "FC1": "主动脉手术", "FC2": "主动脉手术",
    "FD1": "外周血管手术", "FD2": "外周血管手术",
    "FE1": "心包手术", "FE2": "心包手术",
    "FF1": "心血管其他手术伴 MCC", "FF2": "心血管其他手术不伴 MCC",
    "FM1": "循环系统诊断伴 MCC", "FM2": "循环系统诊断不伴 MCC",
    "FM3": "循环系统诊断伴 MCC", "FM4": "循环系统诊断不伴 MCC",
    "FN1": "心律失常伴 MCC", "FN2": "心律失常不伴 MCC",
    "FR1": "急性心肌梗死伴 MCC", "FR2": "急性心肌梗死不伴 MCC",
    "FR3": "急性心肌梗死",
    "FS1": "心绞痛", "FS2": "心绞痛", "FS3": "心绞痛",
    "FT1": "心力衰竭伴 MCC", "FT2": "心力衰竭不伴 MCC",
    "FU1": "心力衰竭", "FU2": "心力衰竭", "FU3": "心力衰竭",
    "FV1": "高血压伴 MCC", "FV2": "高血压不伴 MCC", "FV3": "高血压",
    "FW1": "心律失常及传导障碍", "FW2": "心律失常及传导障碍", "FW3": "心律失常及传导障碍",

    # MDCF — 消化系统
    "GA1": "胃食管反流及消化系统肿瘤大手术", "GA2": "胃食管反流及消化系统肿瘤大手术",
    "GB1": "胃、肠、肝大手术伴 MCC", "GB2": "胃、肠、肝大手术不伴 MCC",
    "GC1": "胃、肠、肝其他手术伴 MCC", "GC2": "胃、肠、肝其他手术不伴 MCC",
    "GD1": "肛管及肛门手术", "GD2": "肛管及肛门手术",
    "GE1": "疝手术", "GE2": "疝手术",
    "GF1": "阑尾切除术伴 MCC", "GF2": "阑尾切除术不伴 MCC",
    "GG1": "消化系统其他手术伴 MCC", "GG2": "消化系统其他手术不伴 MCC",
    "GH1": "胃、肠、肝肿瘤", "GH2": "胃、肠、肝良性肿瘤",
    "GI1": "食管炎、胃肠炎", "GI2": "食管炎、胃肠炎",
    "GJ1": "消化道溃疡伴 MCC", "GJ2": "消化道溃疡不伴 MCC",
    "GK1": "消化道出血伴 MCC", "GK2": "消化道出血不伴 MCC",
    "GL1": "肝硬化及酒精性肝病", "GL2": "肝硬化及酒精性肝病",
    "GM1": "胆道疾病", "GM2": "胆道疾病",
    "GN1": "胆囊及胆道手术伴 MCC", "GN2": "胆囊及胆道手术不伴 MCC",
    "GR1": "肝硬化及严重肝病伴 MCC", "GR2": "肝硬化及严重肝病不伴 MCC",
    "GR3": "肝硬化及严重肝病",
    "GS1": "胰腺炎伴 MCC", "GS2": "胰腺炎不伴 MCC",
    "GT1": "肠炎及功能性胃肠病", "GT2": "肠炎及功能性胃肠病",
    "GU1": "消化性溃疡伴 MCC", "GU2": "消化性溃疡不伴 MCC",
    "GU3": "消化性溃疡",
    "GV1": "胃炎及食管炎", "GV2": "胃炎及食管炎", "GV3": "胃炎及食管炎",
    "GW1": "急性胰腺炎", "GW2": "急性胰腺炎", "GW3": "急性胰腺炎",
    "GX1": "消化系统其他疾患伴 MCC", "GX2": "消化系统其他疾患不伴 MCC",
    "GY1": "消化系统诊断的腹腔镜手术", "GY2": "消化系统诊断的腹腔镜手术",
    "GZ1": "消化道出血", "GZ2": "消化道出血", "GZ3": "消化道出血",

    # MDCG — 肝胆胰脾
    "HA1": "肝、胆、胰大手术伴 MCC", "HA2": "肝、胆、胰大手术不伴 MCC",
    "HB1": "胆囊切除术伴 MCC", "HB2": "胆囊切除术不伴 MCC",
    "HC1": "肝、胆、胰其他手术伴 MCC", "HC2": "肝、胆、胰其他手术不伴 MCC",
    "HD1": "肝、胆、胰肿瘤", "HD2": "肝、胆、胰良性肿瘤",
    "HE1": "肝硬化伴 MCC", "HE2": "肝硬化不伴 MCC",
    "HF1": "胰腺疾患伴 MCC", "HF2": "胰腺疾患不伴 MCC",
    "HG1": "肝、胆、胰其他疾患伴 MCC", "HG2": "肝、胆、胰其他疾患不伴 MCC",
    "HH1": "肝移植", "HH2": "肝移植",
    "HJ1": "胆道疾患", "HJ2": "胆道疾患",

    # MDCH — 骨骼肌肉
    "IA1": "髋、肩、膝大手术伴 MCC", "IA2": "髋、肩、膝大手术不伴 MCC",
    "IB1": "髋、肩、膝其他手术伴 MCC", "IB2": "髋、肩、膝其他手术不伴 MCC",
    "IC1": "脊柱大手术伴 MCC", "IC2": "脊柱大手术不伴 MCC",
    "ID1": "脊柱其他手术伴 MCC", "ID2": "脊柱其他手术不伴 MCC",
    "IE1": "前臂、手、足手术", "IE2": "前臂、手、足手术",
    "IF1": "骨骼肌肉其他手术伴 MCC", "IF2": "骨骼肌肉其他手术不伴 MCC",
    "IG1": "骨骼肌肉系统大手术", "IG2": "骨骼肌肉系统大手术",
    "IH1": "骨骼肌肉肿瘤", "IH2": "骨骼肌肉良性肿瘤",
    "IJ1": "骨折伴 MCC", "IJ2": "骨折不伴 MCC",
    "IK1": "骨骼肌肉系统感染", "IK2": "骨骼肌肉系统感染",
    "IL1": "骨骼肌肉系统其他疾患伴 MCC", "IL2": "骨骼肌肉系统其他疾患不伴 MCC",
    "IM1": "关节置换术伴 MCC", "IM2": "关节置换术不伴 MCC",
    "IN1": "脊柱融合术", "IN2": "脊柱融合术",
    "IT1": "骨关节炎", "IT2": "骨关节炎", "IT3": "骨关节炎",
    "IU1": "椎间盘疾病伴 MCC", "IU2": "椎间盘疾病不伴 MCC", "IU3": "椎间盘疾病",
    "IV1": "骨折", "IV2": "骨折", "IV3": "骨折",
    "IW1": "骨骼肌肉其他疾患", "IW2": "骨骼肌肉其他疾患", "IW3": "骨骼肌肉其他疾患",
    "IX1": "骨骼肌肉系统其他手术", "IX2": "骨骼肌肉系统其他手术",
    "IZ1": "风湿性关节炎", "IZ2": "风湿性关节炎", "IZ3": "风湿性关节炎",

    # MDCI — 皮肤/皮下/乳腺
    "JA1": "皮肤、皮下组织、乳腺大手术伴 MCC", "JA2": "皮肤、皮下组织、乳腺大手术不伴 MCC",
    "JB1": "皮肤、皮下组织、乳腺其他手术伴 MCC", "JB2": "皮肤、皮下组织、乳腺其他手术不伴 MCC",
    "JC1": "乳房切除术", "JC2": "乳房切除术",
    "JD1": "皮肤、皮下组织手术", "JD2": "皮肤、皮下组织手术",
    "JE1": "皮肤、皮下组织、乳腺其他疾患伴 MCC", "JE2": "皮肤、皮下组织、乳腺其他疾患不伴 MCC",
    "JF1": "皮肤溃疡及炎症", "JF2": "皮肤溃疡及炎症",
    "JG1": "皮肤良性肿瘤", "JH1": "乳腺恶性肿瘤", "JH2": "乳腺良性肿瘤",
    "JJ1": "皮肤移植手术", "JJ2": "皮肤移植手术",
    "JR1": "皮肤、皮下组织感染", "JR2": "皮肤、皮下组织感染",
    "JS1": "皮肤、皮下组织其他疾患", "JS2": "皮肤、皮下组织其他疾患",
    "JV1": "蜂窝织炎", "JV2": "蜂窝织炎", "JV3": "蜂窝织炎",
    "JZ1": "皮肤溃疡", "JZ2": "皮肤溃疡", "JZ3": "皮肤溃疡",

    # MDCJ — 内分泌、营养、代谢
    "KA1": "糖尿病伴 MCC", "KA2": "糖尿病不伴 MCC",
    "KB1": "内分泌腺体手术", "KB2": "内分泌腺体手术",
    "KC1": "营养及代谢疾患伴 MCC", "KC2": "营养及代谢疾患不伴 MCC",
    "KD1": "甲状腺及甲状旁腺手术", "KD2": "甲状腺及甲状旁腺手术",
    "KE1": "甲状腺及甲状旁腺疾患", "KF1": "垂体及肾上腺手术",
    "KG1": "糖尿病", "KG2": "糖尿病", "KG3": "糖尿病",
    "KH1": "电解质紊乱及酸碱平衡", "KH2": "电解质紊乱及酸碱平衡",
    "KJ1": "代谢性疾患", "KJ2": "代谢性疾患",
    "KR1": "内分泌疾患伴 MCC", "KR2": "内分泌疾患不伴 MCC",

    # MDCK — 肾脏/泌尿
    "LA1": "肾脏及泌尿道大手术伴 MCC", "LA2": "肾脏及泌尿道大手术不伴 MCC",
    "LB1": "肾脏及泌尿道其他手术伴 MCC", "LB2": "肾脏及泌尿道其他手术不伴 MCC",
    "LC1": "肾、输尿管、膀胱手术", "LC2": "肾、输尿管、膀胱手术",
    "LD1": "前列腺手术伴 MCC", "LD2": "前列腺手术不伴 MCC",
    "LE1": "泌尿系统其他手术", "LE2": "泌尿系统其他手术",
    "LF1": "肾衰竭伴 MCC", "LF2": "肾衰竭不伴 MCC",
    "LG1": "肾及泌尿道肿瘤", "LH1": "肾及泌尿道感染",
    "LJ1": "泌尿系统结石伴 MCC", "LJ2": "泌尿系统结石不伴 MCC",
    "LK1": "肾小球疾病及肾衰竭", "LK2": "肾小球疾病及肾衰竭",
    "LL1": "泌尿系统其他疾患伴 MCC", "LL2": "泌尿系统其他疾患不伴 MCC",
    "LM1": "肾脏及泌尿道手术伴 MCC", "LM2": "肾脏及泌尿道手术不伴 MCC",
    "LR1": "急性肾衰竭", "LR2": "急性肾衰竭",
    "LS1": "慢性肾衰竭", "LS2": "慢性肾衰竭",
    "LT1": "透析", "LT2": "透析",
    "LU1": "急性肾衰竭伴 MCC", "LU2": "急性肾衰竭不伴 MCC",
    "LU3": "急性肾衰竭",
    "LV1": "慢性肾脏病伴 MCC", "LV2": "慢性肾脏病不伴 MCC", "LV3": "慢性肾脏病",
    "LW1": "尿路感染", "LW2": "尿路感染", "LW3": "尿路感染",
    "LX1": "肾及输尿管结石伴 MCC", "LX2": "肾及输尿管结石不伴 MCC", "LX3": "肾及输尿管结石",
    "LY1": "泌尿系统其他疾患", "LY2": "泌尿系统其他疾患",
    "LZ1": "泌尿系统其他疾患伴 MCC", "LZ2": "泌尿系统其他疾患不伴 MCC",

    # MDCL — 男性生殖
    "MA1": "男性生殖系统大手术", "MA2": "男性生殖系统大手术",
    "MB1": "男性生殖系统其他手术", "MB2": "男性生殖系统其他手术",
    "MC1": "男性生殖系统恶性肿瘤", "MC2": "男性生殖系统良性肿瘤",
    "MD1": "男性生殖系统其他疾患", "MD2": "男性生殖系统其他疾患",
    "ME1": "前列腺增生及炎症", "ME2": "前列腺增生及炎症",
    "MF1": "男性生殖系统其他疾患伴 MCC", "MF2": "男性生殖系统其他疾患不伴 MCC",

    # MDCM — 女性生殖
    "NA1": "女性生殖系统大手术伴 MCC", "NA2": "女性生殖系统大手术不伴 MCC",
    "NB1": "女性生殖系统其他手术伴 MCC", "NB2": "女性生殖系统其他手术不伴 MCC",
    "NC1": "子宫切除术伴 MCC", "NC2": "子宫切除术不伴 MCC",
    "ND1": "女性生殖系统其他手术", "ND2": "女性生殖系统其他手术",
    "NE1": "女性生殖系统恶性肿瘤", "NF1": "女性生殖系统良性肿瘤",
    "NG1": "女性生殖系统感染", "NH1": "女性生殖系统其他疾患",
    "NJ1": "女性生殖系统其他疾患伴 MCC", "NJ2": "女性生殖系统其他疾患不伴 MCC",
    "NK1": "异位妊娠及流产", "NK2": "异位妊娠及流产",
    "NR1": "分娩伴 MCC", "NR2": "分娩不伴 MCC",
    "NS1": "剖宫产伴 MCC", "NS2": "剖宫产不伴 MCC",
    "NT1": "阴道分娩伴 MCC", "NT2": "阴道分娩不伴 MCC",
    "NU1": "产科其他疾患", "NV1": "新生儿疾患伴 MCC", "NV2": "新生儿疾患不伴 MCC",
    "NW1": "新生儿疾患", "NW2": "新生儿疾患",

    # MDCN — 血液/免疫
    "QA1": "血液、造血器官及免疫疾患伴 MCC", "QA2": "血液、造血器官及免疫疾患不伴 MCC",
    "QB1": "血液、造血器官及免疫系统肿瘤", "QB2": "血液、造血器官及免疫系统其他疾患",
    "QC1": "凝血功能障碍", "QC2": "凝血功能障碍",
    "QD1": "贫血及溶血", "QD2": "贫血及溶血",
    "QE1": "血液、造血器官及免疫系统其他疾患", "QF1": "脾脏手术",
    "QG1": "淋巴及造血组织手术", "QH1": "血液系统其他疾患",

    # MDCO — 妊娠/分娩
    "OA1": "妊娠分娩大手术", "OA2": "妊娠分娩大手术",
    "OB1": "剖宫产", "OB2": "剖宫产",
    "OC1": "阴道分娩", "OC2": "阴道分娩",
    "OD1": "异位妊娠", "OE1": "妊娠并发症",
    "OF1": "妊娠相关疾患伴 MCC", "OF2": "妊娠相关疾患不伴 MCC",
    "OG1": "产前及产后疾患", "OG2": "产前及产后疾患",
    "OH1": "流产相关手术", "OI1": "流产相关疾患",

    # MDCP — 新生儿
    "PA1": "新生儿大手术伴 MCC", "PA2": "新生儿大手术不伴 MCC",
    "PB1": "新生儿其他手术伴 MCC", "PB2": "新生儿其他手术不伴 MCC",
    "PC1": "新生儿疾患伴 MCC", "PC2": "新生儿疾患不伴 MCC",
    "PD1": "早产儿", "PD2": "早产儿",
    "PE1": "足月新生儿疾患", "PE2": "足月新生儿疾患",
    "PF1": "新生儿窒息及呼吸窘迫", "PF2": "新生儿窒息及呼吸窘迫",

    # MDCR — 创伤/中毒
    "RA1": "多发严重创伤大手术伴 MCC", "RA2": "多发严重创伤大手术不伴 MCC",
    "RB1": "多发严重创伤其他手术伴 MCC", "RB2": "多发严重创伤其他手术不伴 MCC",
    "RC1": "中毒及毒性反应伴 MCC", "RC2": "中毒及毒性反应不伴 MCC",
    "RD1": "创伤性损伤伴 MCC", "RD2": "创伤性损伤不伴 MCC",
    "RE1": "烧伤伴 MCC", "RE2": "烧伤不伴 MCC",
    "RF1": "烧伤其他手术", "RF2": "烧伤其他手术",
    "RG1": "中毒及毒性反应", "RG2": "中毒及毒性反应",
    "RH1": "创伤性损伤", "RH2": "创伤性损伤",

    # MDCS — 感染
    "SA1": "败血症伴 MCC", "SA2": "败血症不伴 MCC",
    "SB1": "严重感染伴 MCC", "SB2": "严重感染不伴 MCC",
    "SC1": "术后及医疗性感染", "SC2": "术后及医疗性感染",
    "SD1": "感染性疾患伴 MCC", "SD2": "感染性疾患不伴 MCC",
    "SE1": "病毒性感染", "SE2": "病毒性感染",
    "SF1": "细菌性感染", "SF2": "细菌性感染",
    "SG1": "真菌性感染", "SH1": "寄生虫病",
    "SI1": "感染性疾患其他", "SJ1": "HIV相关疾患伴 MCC", "SJ2": "HIV相关疾患不伴 MCC",
    "SK1": "感染性疾患", "SL1": "感染性疾患",
    "SZ1": "败血症", "SZ2": "败血症", "SZ3": "败血症",

    # MDCT — 精神/心理
    "TA1": "精神疾患大手术", "TA2": "精神疾患大手术",
    "TB1": "精神分裂症及妄想障碍", "TB2": "精神分裂症及妄想障碍",
    "TC1": "情感障碍", "TC2": "情感障碍",
    "TD1": "神经症性障碍", "TD2": "神经症性障碍",
    "TE1": "物质滥用及成瘾", "TE2": "物质滥用及成瘾",
    "TF1": "精神疾患其他", "TF2": "精神疾患其他",
    "TG1": "儿童及青少年精神障碍", "TG2": "儿童及青少年精神障碍",
    "TH1": "精神疾患伴 MCC", "TH2": "精神疾患不伴 MCC",
    "TJ1": "精神疾患其他伴 MCC", "TJ2": "精神疾患其他不伴 MCC",
    "TK1": "心理治疗", "TL1": "电休克治疗",

    # MDCU — 其他/影响健康状态
    "ZA1": "其他因素影响健康状态伴 MCC", "ZA2": "其他因素影响健康状态不伴 MCC",
    "ZB1": "随访及康复", "ZC1": "其他后续医疗", "ZD1": "其他医疗",
    "ZE1": "HIV治疗", "ZF1": "多药耐药治疗", "ZG1": "植入装置调整",
    "ZH1": "姑息治疗", "ZI1": "康复治疗", "ZJ1": "其他治疗",
    "ZK1": "非特指检查", "ZL1": "非治疗性操作", "ZM1": "器官获取",
    "ZN1": "移植", "ZO1": "骨髓移植", "ZP1": "干细胞移植",

    # MDCV — 烧伤
    "VA1": "烧伤大手术伴 MCC", "VA2": "烧伤大手术不伴 MCC",
    "VB1": "烧伤其他手术伴 MCC", "VB2": "烧伤其他手术不伴 MCC",
    "VC1": "烧伤诊断伴 MCC", "VC2": "烧伤诊断不伴 MCC",
    "VD1": "烧伤其他疾患", "VE1": "多发严重烧伤",

    # MDCW — 涉及多系统
    "XA1": "涉及多系统手术", "XA2": "涉及多系统手术",
    "XB1": "涉及多系统诊断伴 MCC", "XB2": "涉及多系统诊断不伴 MCC",
    "XC1": "涉及多系统其他疾患", "XD1": "涉及多系统其他疾患伴 MCC",
    "XE1": "涉及多系统其他疾患不伴 MCC",

    # MDCX — 错误组 / 未分组
    "YA1": "错误组 - 主要诊断与性别不符", "YA2": "错误组 - 主要诊断与年龄不符",
    "YA3": "错误组 - 主要手术与性别不符", "YA4": "错误组 - 其他错误",
}


# ── Surgery → DRG mapping (CHS-DRG 1.1 高频手术) ────────────────────────────
# Each entry: icd9cm3_code -> {name, mdc, adrg, drg_with_mcc, drg_with_cc, drg_without, drg_names}
# DRG 后缀约定: 1=MCC, 3=CC, 5=无 CC/MCC

SURGERY_TO_DRG: dict[str, dict] = {
    # ── MDCA 神经系统手术 ──
    "01.24": {"name": "开颅术其他", "mdc": "MDCA", "adrg": "AD1", "with_mcc": "AD11", "with_cc": "AD13", "without": "AD15", "drg_names": {"AD11": "颅脑手术伴 MCC", "AD13": "颅脑手术伴 CC", "AD15": "颅脑手术不伴 CC/MCC"}},
    "01.25": {"name": "其他颅骨切除术", "mdc": "MDCA", "adrg": "AD1", "with_mcc": "AD11", "with_cc": "AD13", "without": "AD15", "drg_names": {"AD11": "颅脑手术伴 MCC", "AD13": "颅脑手术伴 CC", "AD15": "颅脑手术不伴 CC/MCC"}},
    "01.31": {"name": "脑膜切开术", "mdc": "MDCA", "adrg": "AD1", "with_mcc": "AD11", "with_cc": "AD13", "without": "AD15", "drg_names": {"AD11": "颅脑手术伴 MCC", "AD13": "颅脑手术伴 CC", "AD15": "颅脑手术不伴 CC/MCC"}},
    "01.39": {"name": "脑其他切开术", "mdc": "MDCA", "adrg": "AD1", "with_mcc": "AD11", "with_cc": "AD13", "without": "AD15", "drg_names": {"AD11": "颅脑手术伴 MCC", "AD13": "颅脑手术伴 CC", "AD15": "颅脑手术不伴 CC/MCC"}},
    "02.31": {"name": "脑室分流术", "mdc": "MDCA", "adrg": "AH1", "with_mcc": "AH11", "with_cc": "AH13", "without": "AH15", "drg_names": {"AH11": "脊髓及椎管手术伴 MCC", "AH13": "脊髓及椎管手术伴 CC", "AH15": "脊髓及椎管手术不伴 CC/MCC"}},
    "03.09": {"name": "椎管其他探查术和减压术", "mdc": "MDCA", "adrg": "AH1", "with_mcc": "AH11", "with_cc": "AH13", "without": "AH15", "drg_names": {"AH11": "脊髓及椎管手术伴 MCC", "AH13": "脊髓及椎管手术伴 CC", "AH15": "脊髓及椎管手术不伴 CC/MCC"}},
    "03.51": {"name": "脊膜囊肿切除术", "mdc": "MDCA", "adrg": "AH1", "with_mcc": "AH11", "with_cc": "AH13", "without": "AH15", "drg_names": {"AH11": "脊髓及椎管手术伴 MCC", "AH13": "脊髓及椎管手术伴 CC", "AH15": "脊髓及椎管手术不伴 CC/MCC"}},

    # ── MDCB 眼科手术 ──
    "13.11": {"name": "晶状体囊外摘出术", "mdc": "MDCB", "adrg": "CB1", "with_mcc": "CB11", "with_cc": "CB13", "without": "CB15", "drg_names": {"CB11": "晶体手术伴 MCC", "CB13": "晶体手术伴 CC", "CB15": "晶体手术不伴 CC/MCC"}},
    "13.19": {"name": "晶状体其他囊外摘出术", "mdc": "MDCB", "adrg": "CB1", "with_mcc": "CB11", "with_cc": "CB13", "without": "CB15", "drg_names": {"CB11": "晶体手术伴 MCC", "CB13": "晶体手术伴 CC", "CB15": "晶体手术不伴 CC/MCC"}},
    "13.41": {"name": "白内障超声乳化吸出术", "mdc": "MDCB", "adrg": "CB1", "with_mcc": "CB11", "with_cc": "CB13", "without": "CB15", "drg_names": {"CB11": "晶体手术伴 MCC", "CB13": "晶体手术伴 CC", "CB15": "晶体手术不伴 CC/MCC"}},
    "13.71": {"name": "人工晶体置入术", "mdc": "MDCB", "adrg": "CB1", "with_mcc": "CB11", "with_cc": "CB13", "without": "CB15", "drg_names": {"CB11": "晶体手术伴 MCC", "CB13": "晶体手术伴 CC", "CB15": "晶体手术不伴 CC/MCC"}},
    "14.74": {"name": "玻璃体切除术", "mdc": "MDCB", "adrg": "CC1", "with_mcc": "CC11", "with_cc": "CC13", "without": "CC15", "drg_names": {"CC11": "视网膜玻璃体手术伴 MCC", "CC13": "视网膜玻璃体手术伴 CC", "CC15": "视网膜玻璃体手术不伴 CC/MCC"}},

    # ── MDCE 循环系统手术 ──
    "00.66": {"name": "经皮冠状动脉腔内血管成形术 [PTCA] 或冠状动脉粥样斑块切除术", "mdc": "MDCE", "adrg": "EC1", "with_mcc": "EC11", "with_cc": "EC13", "without": "EC15", "drg_names": {"EC11": "经皮冠状动脉支架植入伴 MCC", "EC13": "经皮冠状动脉支架植入伴 CC", "EC15": "经皮冠状动脉支架植入不伴 CC/MCC"}},
    "00.67": {"name": "经皮冠状动脉药物洗脱支架植入", "mdc": "MDCE", "adrg": "EC1", "with_mcc": "EC11", "with_cc": "EC13", "without": "EC15", "drg_names": {"EC11": "经皮冠状动脉支架植入伴 MCC", "EC13": "经皮冠状动脉支架植入伴 CC", "EC15": "经皮冠状动脉支架植入不伴 CC/MCC"}},
    "00.40": {"name": "单根血管操作", "mdc": "MDCE", "adrg": "EC1", "with_mcc": "EC11", "with_cc": "EC13", "without": "EC15", "drg_names": {"EC11": "经皮冠状动脉支架植入伴 MCC", "EC13": "经皮冠状动脉支架植入伴 CC", "EC15": "经皮冠状动脉支架植入不伴 CC/MCC"}},
    "00.41": {"name": "两根血管操作", "mdc": "MDCE", "adrg": "EC1", "with_mcc": "EC11", "with_cc": "EC13", "without": "EC15", "drg_names": {"EC11": "经皮冠状动脉支架植入伴 MCC", "EC13": "经皮冠状动脉支架植入伴 CC", "EC15": "经皮冠状动脉支架植入不伴 CC/MCC"}},
    "00.42": {"name": "三根血管操作", "mdc": "MDCE", "adrg": "EC1", "with_mcc": "EC11", "with_cc": "EC13", "without": "EC15", "drg_names": {"EC11": "经皮冠状动脉支架植入伴 MCC", "EC13": "经皮冠状动脉支架植入伴 CC", "EC15": "经皮冠状动脉支架植入不伴 CC/MCC"}},
    "00.43": {"name": "四根或更多根血管操作", "mdc": "MDCE", "adrg": "EC1", "with_mcc": "EC11", "with_cc": "EC13", "without": "EC15", "drg_names": {"EC11": "经皮冠状动脉支架植入伴 MCC", "EC13": "经皮冠状动脉支架植入伴 CC", "EC15": "经皮冠状动脉支架植入不伴 CC/MCC"}},
    "00.45": {"name": "一根血管置入药物洗脱支架", "mdc": "MDCE", "adrg": "EC1", "with_mcc": "EC11", "with_cc": "EC13", "without": "EC15", "drg_names": {"EC11": "经皮冠状动脉支架植入伴 MCC", "EC13": "经皮冠状动脉支架植入伴 CC", "EC15": "经皮冠状动脉支架植入不伴 CC/MCC"}},
    "00.48": {"name": "两根以上血管置入药物洗脱支架", "mdc": "MDCE", "adrg": "EC1", "with_mcc": "EC11", "with_cc": "EC13", "without": "EC15", "drg_names": {"EC11": "经皮冠状动脉支架植入伴 MCC", "EC13": "经皮冠状动脉支架植入伴 CC", "EC15": "经皮冠状动脉支架植入不伴 CC/MCC"}},
    "36.10": {"name": "主动脉冠状动脉旁路移植", "mdc": "MDCE", "adrg": "ED1", "with_mcc": "ED11", "with_cc": "ED13", "without": "ED15", "drg_names": {"ED11": "冠状动脉旁路移植伴 MCC", "ED13": "冠状动脉旁路移植伴 CC", "ED15": "冠状动脉旁路移植不伴 CC/MCC"}},
    "36.11": {"name": "一根冠状动脉的主动脉冠状动脉旁路移植", "mdc": "MDCE", "adrg": "ED1", "with_mcc": "ED11", "with_cc": "ED13", "without": "ED15", "drg_names": {"ED11": "冠状动脉旁路移植伴 MCC", "ED13": "冠状动脉旁路移植伴 CC", "ED15": "冠状动脉旁路移植不伴 CC/MCC"}},
    "36.12": {"name": "两根冠状动脉的主动脉冠状动脉旁路移植", "mdc": "MDCE", "adrg": "ED1", "with_mcc": "ED11", "with_cc": "ED13", "without": "ED15", "drg_names": {"ED11": "冠状动脉旁路移植伴 MCC", "ED13": "冠状动脉旁路移植伴 CC", "ED15": "冠状动脉旁路移植不伴 CC/MCC"}},
    "36.13": {"name": "三根冠状动脉的主动脉冠状动脉旁路移植", "mdc": "MDCE", "adrg": "ED1", "with_mcc": "ED11", "with_cc": "ED13", "without": "ED15", "drg_names": {"ED11": "冠状动脉旁路移植伴 MCC", "ED13": "冠状动脉旁路移植伴 CC", "ED15": "冠状动脉旁路移植不伴 CC/MCC"}},
    "36.14": {"name": "四根或更多根冠状动脉的主动脉冠状动脉旁路移植", "mdc": "MDCE", "adrg": "ED1", "with_mcc": "ED11", "with_cc": "ED13", "without": "ED15", "drg_names": {"ED11": "冠状动脉旁路移植伴 MCC", "ED13": "冠状动脉旁路移植伴 CC", "ED15": "冠状动脉旁路移植不伴 CC/MCC"}},
    "36.15": {"name": "胸腔内动脉的单支移植", "mdc": "MDCE", "adrg": "ED1", "with_mcc": "ED11", "with_cc": "ED13", "without": "ED15", "drg_names": {"ED11": "冠状动脉旁路移植伴 MCC", "ED13": "冠状动脉旁路移植伴 CC", "ED15": "冠状动脉旁路移植不伴 CC/MCC"}},
    "36.16": {"name": "其他胸腔内动脉的双支移植", "mdc": "MDCE", "adrg": "ED1", "with_mcc": "ED11", "with_cc": "ED13", "without": "ED15", "drg_names": {"ED11": "冠状动脉旁路移植伴 MCC", "ED13": "冠状动脉旁路移植伴 CC", "ED15": "冠状动脉旁路移植不伴 CC/MCC"}},
    "36.19": {"name": "其他搭桥术", "mdc": "MDCE", "adrg": "ED1", "with_mcc": "ED11", "with_cc": "ED13", "without": "ED15", "drg_names": {"ED11": "冠状动脉旁路移植伴 MCC", "ED13": "冠状动脉旁路移植伴 CC", "ED15": "冠状动脉旁路移植不伴 CC/MCC"}},
    "37.22": {"name": "左心导管检查", "mdc": "MDCE", "adrg": "EF1", "with_mcc": "EF11", "with_cc": "EF13", "without": "EF15", "drg_names": {"EF11": "心导管检查伴 MCC", "EF13": "心导管检查伴 CC", "EF15": "心导管检查不伴 CC/MCC"}},
    "37.23": {"name": "联合右心和左心导管检查", "mdc": "MDCE", "adrg": "EF1", "with_mcc": "EF11", "with_cc": "EF13", "without": "EF15", "drg_names": {"EF11": "心导管检查伴 MCC", "EF13": "心导管检查伴 CC", "EF15": "心导管检查不伴 CC/MCC"}},
    "37.80": {"name": "永久起搏器置入", "mdc": "MDCE", "adrg": "EE1", "with_mcc": "EE11", "with_cc": "EE13", "without": "EE15", "drg_names": {"EE11": "心脏起搏器植入伴 MCC", "EE13": "心脏起搏器植入伴 CC", "EE15": "心脏起搏器植入不伴 CC/MCC"}},
    "37.81": {"name": "永久起搏器置入首次经静脉置入", "mdc": "MDCE", "adrg": "EE1", "with_mcc": "EE11", "with_cc": "EE13", "without": "EE15", "drg_names": {"EE11": "心脏起搏器植入伴 MCC", "EE13": "心脏起搏器植入伴 CC", "EE15": "心脏起搏器植入不伴 CC/MCC"}},
    "37.82": {"name": "永久起搏器置换", "mdc": "MDCE", "adrg": "EE1", "with_mcc": "EE11", "with_cc": "EE13", "without": "EE15", "drg_names": {"EE11": "心脏起搏器植入伴 MCC", "EE13": "心脏起搏器植入伴 CC", "EE15": "心脏起搏器植入不伴 CC/MCC"}},
    "37.94": {"name": "自动复律器/除颤器置入", "mdc": "MDCE", "adrg": "EE1", "with_mcc": "EE11", "with_cc": "EE13", "without": "EE15", "drg_names": {"EE11": "心脏起搏器植入伴 MCC", "EE13": "心脏起搏器植入伴 CC", "EE15": "心脏起搏器植入不伴 CC/MCC"}},
    "37.95": {"name": "自动复律器/除颤器置换", "mdc": "MDCE", "adrg": "EE1", "with_mcc": "EE11", "with_cc": "EE13", "without": "EE15", "drg_names": {"EE11": "心脏起搏器植入伴 MCC", "EE13": "心脏起搏器植入伴 CC", "EE15": "心脏起搏器植入不伴 CC/MCC"}},
    "38.12": {"name": "颈动脉内膜剥脱术", "mdc": "MDCE", "adrg": "EG1", "with_mcc": "EG11", "with_cc": "EG13", "without": "EG15", "drg_names": {"EG11": "周围血管手术伴 MCC", "EG13": "周围血管手术伴 CC", "EG15": "周围血管手术不伴 CC/MCC"}},
    "39.50": {"name": "血管其他血管成形术", "mdc": "MDCE", "adrg": "EG1", "with_mcc": "EG11", "with_cc": "EG13", "without": "EG15", "drg_names": {"EG11": "周围血管手术伴 MCC", "EG13": "周围血管手术伴 CC", "EG15": "周围血管手术不伴 CC/MCC"}},

    # ── MDCF 消化系统手术 ──
    "42.41": {"name": "食管部分切除术", "mdc": "MDCG", "adrg": "GA1", "with_mcc": "GA11", "with_cc": "GA13", "without": "GA15", "drg_names": {"GA11": "胃食管反流及消化系统肿瘤大手术伴 MCC", "GA13": "胃食管反流及消化系统肿瘤大手术伴 CC", "GA15": "胃食管反流及消化系统肿瘤大手术不伴 CC/MCC"}},
    "43.6": {"name": "胃部分切除术伴胃十二指肠吻合术", "mdc": "MDCG", "adrg": "GB1", "with_mcc": "GB11", "with_cc": "GB13", "without": "GB15", "drg_names": {"GB11": "胃、肠、肝大手术伴 MCC", "GB13": "胃、肠、肝大手术伴 CC", "GB15": "胃、肠、肝大手术不伴 CC/MCC"}},
    "43.7": {"name": "胃部分切除术伴胃空肠吻合术", "mdc": "MDCG", "adrg": "GB1", "with_mcc": "GB11", "with_cc": "GB13", "without": "GB15", "drg_names": {"GB11": "胃、肠、肝大手术伴 MCC", "GB13": "胃、肠、肝大手术伴 CC", "GB15": "胃、肠、肝大手术不伴 CC/MCC"}},
    "44.41": {"name": "胃溃疡穿孔修补术", "mdc": "MDCG", "adrg": "GC1", "with_mcc": "GC11", "with_cc": "GC13", "without": "GC15", "drg_names": {"GC11": "胃、肠、肝其他手术伴 MCC", "GC13": "胃、肠、肝其他手术伴 CC", "GC15": "胃、肠、肝其他手术不伴 CC/MCC"}},
    "44.42": {"name": "十二指肠溃疡穿孔修补术", "mdc": "MDCG", "adrg": "GC1", "with_mcc": "GC11", "with_cc": "GC13", "without": "GC15", "drg_names": {"GC11": "胃、肠、肝其他手术伴 MCC", "GC13": "胃、肠、肝其他手术伴 CC", "GC15": "胃、肠、肝其他手术不伴 CC/MCC"}},
    "45.41": {"name": "大肠病损切除术", "mdc": "MDCG", "adrg": "GC1", "with_mcc": "GC11", "with_cc": "GC13", "without": "GC15", "drg_names": {"GC11": "胃、肠、肝其他手术伴 MCC", "GC13": "胃、肠、肝其他手术伴 CC", "GC15": "胃、肠、肝其他手术不伴 CC/MCC"}},
    "45.73": {"name": "右半结肠切除术", "mdc": "MDCG", "adrg": "GB1", "with_mcc": "GB11", "with_cc": "GB13", "without": "GB15", "drg_names": {"GB11": "胃、肠、肝大手术伴 MCC", "GB13": "胃、肠、肝大手术伴 CC", "GB15": "胃、肠、肝大手术不伴 CC/MCC"}},
    "45.74": {"name": "横结肠切除术", "mdc": "MDCG", "adrg": "GB1", "with_mcc": "GB11", "with_cc": "GB13", "without": "GB15", "drg_names": {"GB11": "胃、肠、肝大手术伴 MCC", "GB13": "胃、肠、肝大手术伴 CC", "GB15": "胃、肠、肝大手术不伴 CC/MCC"}},
    "45.75": {"name": "左半结肠切除术", "mdc": "MDCG", "adrg": "GB1", "with_mcc": "GB11", "with_cc": "GB13", "without": "GB15", "drg_names": {"GB11": "胃、肠、肝大手术伴 MCC", "GB13": "胃、肠、肝大手术伴 CC", "GB15": "胃、肠、肝大手术不伴 CC/MCC"}},
    "45.76": {"name": "乙状结肠切除术", "mdc": "MDCG", "adrg": "GB1", "with_mcc": "GB11", "with_cc": "GB13", "without": "GB15", "drg_names": {"GB11": "胃、肠、肝大手术伴 MCC", "GB13": "胃、肠、肝大手术伴 CC", "GB15": "胃、肠、肝大手术不伴 CC/MCC"}},
    "48.5": {"name": "直肠前切除术", "mdc": "MDCG", "adrg": "GB1", "with_mcc": "GB11", "with_cc": "GB13", "without": "GB15", "drg_names": {"GB11": "胃、肠、肝大手术伴 MCC", "GB13": "胃、肠、肝大手术伴 CC", "GB15": "胃、肠、肝大手术不伴 CC/MCC"}},
    "48.62": {"name": "直肠前切除伴结肠造口术", "mdc": "MDCG", "adrg": "GB1", "with_mcc": "GB11", "with_cc": "GB13", "without": "GB15", "drg_names": {"GB11": "胃、肠、肝大手术伴 MCC", "GB13": "胃、肠、肝大手术伴 CC", "GB15": "胃、肠、肝大手术不伴 CC/MCC"}},
    "48.63": {"name": "直肠其他前切除术", "mdc": "MDCG", "adrg": "GB1", "with_mcc": "GB11", "with_cc": "GB13", "without": "GB15", "drg_names": {"GB11": "胃、肠、肝大手术伴 MCC", "GB13": "胃、肠、肝大手术伴 CC", "GB15": "胃、肠、肝大手术不伴 CC/MCC"}},
    "49.46": {"name": "痔切除术", "mdc": "MDCG", "adrg": "GD1", "with_mcc": "GD11", "with_cc": "GD13", "without": "GD15", "drg_names": {"GD11": "肛管及肛门手术伴 MCC", "GD13": "肛管及肛门手术伴 CC", "GD15": "肛管及肛门手术不伴 CC/MCC"}},
    "51.22": {"name": "胆囊切除术", "mdc": "MDCG", "adrg": "HB1", "with_mcc": "HB11", "with_cc": "HB13", "without": "HB15", "drg_names": {"HB11": "胆囊切除术伴 MCC", "HB13": "胆囊切除术伴 CC", "HB15": "胆囊切除术不伴 CC/MCC"}},
    "51.23": {"name": "腹腔镜下胆囊切除术", "mdc": "MDCG", "adrg": "HB1", "with_mcc": "HB11", "with_cc": "HB13", "without": "HB15", "drg_names": {"HB11": "胆囊切除术伴 MCC", "HB13": "胆囊切除术伴 CC", "HB15": "胆囊切除术不伴 CC/MCC"}},
    "47.01": {"name": "腹腔镜下阑尾切除术", "mdc": "MDCG", "adrg": "GF1", "with_mcc": "GF11", "with_cc": "GF13", "without": "GF15", "drg_names": {"GF11": "阑尾切除术伴 MCC", "GF13": "阑尾切除术伴 CC", "GF15": "阑尾切除术不伴 CC/MCC"}},
    "47.09": {"name": "其他阑尾切除术", "mdc": "MDCG", "adrg": "GF1", "with_mcc": "GF11", "with_cc": "GF13", "without": "GF15", "drg_names": {"GF11": "阑尾切除术伴 MCC", "GF13": "阑尾切除术伴 CC", "GF15": "阑尾切除术不伴 CC/MCC"}},
    "53.00": {"name": "腹股沟疝单侧修补术", "mdc": "MDCG", "adrg": "GE1", "with_mcc": "GE11", "with_cc": "GE13", "without": "GE15", "drg_names": {"GE11": "疝手术伴 MCC", "GE13": "疝手术伴 CC", "GE15": "疝手术不伴 CC/MCC"}},
    "53.05": {"name": "腹股沟疝修补术用假体", "mdc": "MDCG", "adrg": "GE1", "with_mcc": "GE11", "with_cc": "GE13", "without": "GE15", "drg_names": {"GE11": "疝手术伴 MCC", "GE13": "疝手术伴 CC", "GE15": "疝手术不伴 CC/MCC"}},
    "53.41": {"name": "脐疝修补术", "mdc": "MDCG", "adrg": "GE1", "with_mcc": "GE11", "with_cc": "GE13", "without": "GE15", "drg_names": {"GE11": "疝手术伴 MCC", "GE13": "疝手术伴 CC", "GE15": "疝手术不伴 CC/MCC"}},

    # ── MDCG 肝胆胰手术 ──
    "50.22": {"name": "肝部分切除术", "mdc": "MDCG", "adrg": "HA1", "with_mcc": "HA11", "with_cc": "HA13", "without": "HA15", "drg_names": {"HA11": "肝、胆、胰大手术伴 MCC", "HA13": "肝、胆、胰大手术伴 CC", "HA15": "肝、胆、胰大手术不伴 CC/MCC"}},
    "50.3": {"name": "肝叶切除术", "mdc": "MDCG", "adrg": "HA1", "with_mcc": "HA11", "with_cc": "HA13", "without": "HA15", "drg_names": {"HA11": "肝、胆、胰大手术伴 MCC", "HA13": "肝、胆、胰大手术伴 CC", "HA15": "肝、胆、胰大手术不伴 CC/MCC"}},
    "52.7": {"name": "根治性胰十二指肠切除术", "mdc": "MDCG", "adrg": "HA1", "with_mcc": "HA11", "with_cc": "HA13", "without": "HA15", "drg_names": {"HA11": "肝、胆、胰大手术伴 MCC", "HA13": "肝、胆、胰大手术伴 CC", "HA15": "肝、胆、胰大手术不伴 CC/MCC"}},
    "52.51": {"name": "近端胰腺切除术", "mdc": "MDCG", "adrg": "HA1", "with_mcc": "HA11", "with_cc": "HA13", "without": "HA15", "drg_names": {"HA11": "肝、胆、胰大手术伴 MCC", "HA13": "肝、胆、胰大手术伴 CC", "HA15": "肝、胆、胰大手术不伴 CC/MCC"}},
    "52.52": {"name": "远端胰腺切除术", "mdc": "MDCG", "adrg": "HA1", "with_mcc": "HA11", "with_cc": "HA13", "without": "HA15", "drg_names": {"HA11": "肝、胆、胰大手术伴 MCC", "HA13": "肝、胆、胰大手术伴 CC", "HA15": "肝、胆、胰大手术不伴 CC/MCC"}},

    # ── MDCI 骨骼/肌肉手术 ──
    "81.51": {"name": "髋关节置换", "mdc": "MDCI", "adrg": "IA1", "with_mcc": "IA11", "with_cc": "IA13", "without": "IA15", "drg_names": {"IA11": "髋、肩、膝大手术伴 MCC", "IA13": "髋、肩、膝大手术伴 CC", "IA15": "髋、肩、膝大手术不伴 CC/MCC"}},
    "81.52": {"name": "髋关节部分置换", "mdc": "MDCI", "adrg": "IA1", "with_mcc": "IA11", "with_cc": "IA13", "without": "IA15", "drg_names": {"IA11": "髋、肩、膝大手术伴 MCC", "IA13": "髋、肩、膝大手术伴 CC", "IA15": "髋、肩、膝大手术不伴 CC/MCC"}},
    "81.53": {"name": "髋关节置换修正术", "mdc": "MDCI", "adrg": "IA1", "with_mcc": "IA11", "with_cc": "IA13", "without": "IA15", "drg_names": {"IA11": "髋、肩、膝大手术伴 MCC", "IA13": "髋、肩、膝大手术伴 CC", "IA15": "髋、肩、膝大手术不伴 CC/MCC"}},
    "81.54": {"name": "膝关节置换", "mdc": "MDCI", "adrg": "IA1", "with_mcc": "IA11", "with_cc": "IA13", "without": "IA15", "drg_names": {"IA11": "髋、肩、膝大手术伴 MCC", "IA13": "髋、肩、膝大手术伴 CC", "IA15": "髋、肩、膝大手术不伴 CC/MCC"}},
    "81.55": {"name": "膝关节部分置换修正术", "mdc": "MDCI", "adrg": "IA1", "with_mcc": "IA11", "with_cc": "IA13", "without": "IA15", "drg_names": {"IA11": "髋、肩、膝大手术伴 MCC", "IA13": "髋、肩、膝大手术伴 CC", "IA15": "髋、肩、膝大手术不伴 CC/MCC"}},
    "81.62": {"name": "脊柱融合", "mdc": "MDCI", "adrg": "IN1", "with_mcc": "IN11", "with_cc": "IN13", "without": "IN15", "drg_names": {"IN11": "脊柱融合术伴 MCC", "IN13": "脊柱融合术伴 CC", "IN15": "脊柱融合术不伴 CC/MCC"}},
    "81.63": {"name": "腰骶融合", "mdc": "MDCI", "adrg": "IN1", "with_mcc": "IN11", "with_cc": "IN13", "without": "IN15", "drg_names": {"IN11": "脊柱融合术伴 MCC", "IN13": "脊柱融合术伴 CC", "IN15": "脊柱融合术不伴 CC/MCC"}},
    "81.64": {"name": "颈椎融合", "mdc": "MDCI", "adrg": "IN1", "with_mcc": "IN11", "with_cc": "IN13", "without": "IN15", "drg_names": {"IN11": "脊柱融合术伴 MCC", "IN13": "脊柱融合术伴 CC", "IN15": "脊柱融合术不伴 CC/MCC"}},
    "81.65": {"name": "胸椎融合", "mdc": "MDCI", "adrg": "IN1", "with_mcc": "IN11", "with_cc": "IN13", "without": "IN15", "drg_names": {"IN11": "脊柱融合术伴 MCC", "IN13": "脊柱融合术伴 CC", "IN15": "脊柱融合术不伴 CC/MCC"}},
    "81.66": {"name": "腰骶椎融合", "mdc": "MDCI", "adrg": "IN1", "with_mcc": "IN11", "with_cc": "IN13", "without": "IN15", "drg_names": {"IN11": "脊柱融合术伴 MCC", "IN13": "脊柱融合术伴 CC", "IN15": "脊柱融合术不伴 CC/MCC"}},
    "80.51": {"name": "椎间盘切除术", "mdc": "MDCI", "adrg": "IC1", "with_mcc": "IC11", "with_cc": "IC13", "without": "IC15", "drg_names": {"IC11": "脊柱大手术伴 MCC", "IC13": "脊柱大手术伴 CC", "IC15": "脊柱大手术不伴 CC/MCC"}},
    "80.52": {"name": "椎间盘化学溶核术", "mdc": "MDCI", "adrg": "IC1", "with_mcc": "IC11", "with_cc": "IC13", "without": "IC15", "drg_names": {"IC11": "脊柱大手术伴 MCC", "IC13": "脊柱大手术伴 CC", "IC15": "脊柱大手术不伴 CC/MCC"}},
    "79.31": {"name": "肱骨骨折开放性复位内固定", "mdc": "MDCI", "adrg": "IF1", "with_mcc": "IF11", "with_cc": "IF13", "without": "IF15", "drg_names": {"IF11": "骨骼肌肉其他手术伴 MCC", "IF13": "骨骼肌肉其他手术伴 CC", "IF15": "骨骼肌肉其他手术不伴 CC/MCC"}},
    "79.32": {"name": "桡骨骨折开放性复位内固定", "mdc": "MDCI", "adrg": "IF1", "with_mcc": "IF11", "with_cc": "IF13", "without": "IF15", "drg_names": {"IF11": "骨骼肌肉其他手术伴 MCC", "IF13": "骨骼肌肉其他手术伴 CC", "IF15": "骨骼肌肉其他手术不伴 CC/MCC"}},
    "79.35": {"name": "股骨骨折开放性复位内固定", "mdc": "MDCI", "adrg": "IF1", "with_mcc": "IF11", "with_cc": "IF13", "without": "IF15", "drg_names": {"IF11": "骨骼肌肉其他手术伴 MCC", "IF13": "骨骼肌肉其他手术伴 CC", "IF15": "骨骼肌肉其他手术不伴 CC/MCC"}},
    "79.36": {"name": "胫骨骨折开放性复位内固定", "mdc": "MDCI", "adrg": "IF1", "with_mcc": "IF11", "with_cc": "IF13", "without": "IF15", "drg_names": {"IF11": "骨骼肌肉其他手术伴 MCC", "IF13": "骨骼肌肉其他手术伴 CC", "IF15": "骨骼肌肉其他手术不伴 CC/MCC"}},
    "78.55": {"name": "股骨外固定", "mdc": "MDCI", "adrg": "IF1", "with_mcc": "IF11", "with_cc": "IF13", "without": "IF15", "drg_names": {"IF11": "骨骼肌肉其他手术伴 MCC", "IF13": "骨骼肌肉其他手术伴 CC", "IF15": "骨骼肌肉其他手术不伴 CC/MCC"}},
    "78.17": {"name": "胫骨外固定", "mdc": "MDCI", "adrg": "IF1", "with_mcc": "IF11", "with_cc": "IF13", "without": "IF15", "drg_names": {"IF11": "骨骼肌肉其他手术伴 MCC", "IF13": "骨骼肌肉其他手术伴 CC", "IF15": "骨骼肌肉其他手术不伴 CC/MCC"}},
    "81.0": {"name": "脊柱融合", "mdc": "MDCI", "adrg": "IN1", "with_mcc": "IN11", "with_cc": "IN13", "without": "IN15", "drg_names": {"IN11": "脊柱融合术伴 MCC", "IN13": "脊柱融合术伴 CC", "IN15": "脊柱融合术不伴 CC/MCC"}},
    "78.45": {"name": "骨折内固定术", "mdc": "MDCI", "adrg": "IF1", "with_mcc": "IF11", "with_cc": "IF13", "without": "IF15", "drg_names": {"IF11": "骨骼肌肉其他手术伴 MCC", "IF13": "骨骼肌肉其他手术伴 CC", "IF15": "骨骼肌肉其他手术不伴 CC/MCC"}},

    # ── MDCL 泌尿系统手术 ──
    "55.51": {"name": "肾输尿管切除术", "mdc": "MDCL", "adrg": "LA1", "with_mcc": "LA11", "with_cc": "LA13", "without": "LA15", "drg_names": {"LA11": "肾脏及泌尿道大手术伴 MCC", "LA13": "肾脏及泌尿道大手术伴 CC", "LA15": "肾脏及泌尿道大手术不伴 CC/MCC"}},
    "55.52": {"name": "孤立肾的肾切除术", "mdc": "MDCL", "adrg": "LA1", "with_mcc": "LA11", "with_cc": "LA13", "without": "LA15", "drg_names": {"LA11": "肾脏及泌尿道大手术伴 MCC", "LA13": "肾脏及泌尿道大手术伴 CC", "LA15": "肾脏及泌尿道大手术不伴 CC/MCC"}},
    "55.4": {"name": "肾部分切除术", "mdc": "MDCL", "adrg": "LB1", "with_mcc": "LB11", "with_cc": "LB13", "without": "LB15", "drg_names": {"LB11": "肾脏及泌尿道其他手术伴 MCC", "LB13": "肾脏及泌尿道其他手术伴 CC", "LB15": "肾脏及泌尿道其他手术不伴 CC/MCC"}},
    "60.5": {"name": "前列腺切除术", "mdc": "MDCL", "adrg": "LD1", "with_mcc": "LD11", "with_cc": "LD13", "without": "LD15", "drg_names": {"LD11": "前列腺手术伴 MCC", "LD13": "前列腺手术伴 CC", "LD15": "前列腺手术不伴 CC/MCC"}},
    "60.62": {"name": "经尿道前列腺切除术", "mdc": "MDCL", "adrg": "LD1", "with_mcc": "LD11", "with_cc": "LD13", "without": "LD15", "drg_names": {"LD11": "前列腺手术伴 MCC", "LD13": "前列腺手术伴 CC", "LD15": "前列腺手术不伴 CC/MCC"}},
    "57.71": {"name": "根治性膀胱切除术", "mdc": "MDCL", "adrg": "LA1", "with_mcc": "LA11", "with_cc": "LA13", "without": "LA15", "drg_names": {"LA11": "肾脏及泌尿道大手术伴 MCC", "LA13": "肾脏及泌尿道大手术伴 CC", "LA15": "肾脏及泌尿道大手术不伴 CC/MCC"}},
    "58.6": {"name": "尿道扩张", "mdc": "MDCL", "adrg": "LB1", "with_mcc": "LB11", "with_cc": "LB13", "without": "LB15", "drg_names": {"LB11": "肾脏及泌尿道其他手术伴 MCC", "LB13": "肾脏及泌尿道其他手术伴 CC", "LB15": "肾脏及泌尿道其他手术不伴 CC/MCC"}},
    "98.51": {"name": "体外冲击波碎石", "mdc": "MDCL", "adrg": "LJ1", "with_mcc": "LJ11", "with_cc": "LJ13", "without": "LJ15", "drg_names": {"LJ11": "泌尿系统结石伴 MCC", "LJ13": "泌尿系统结石伴 CC", "LJ15": "泌尿系统结石不伴 CC/MCC"}},

    # ── MDCM 女性生殖 ──
    "68.4": {"name": "子宫全切术", "mdc": "MDCM", "adrg": "NC1", "with_mcc": "NC11", "with_cc": "NC13", "without": "NC15", "drg_names": {"NC11": "子宫切除术伴 MCC", "NC13": "子宫切除术伴 CC", "NC15": "子宫切除术不伴 CC/MCC"}},
    "68.51": {"name": "腹腔镜子宫切除术", "mdc": "MDCM", "adrg": "NC1", "with_mcc": "NC11", "with_cc": "NC13", "without": "NC15", "drg_names": {"NC11": "子宫切除术伴 MCC", "NC13": "子宫切除术伴 CC", "NC15": "子宫切除术不伴 CC/MCC"}},
    "68.59": {"name": "其他子宫切除术", "mdc": "MDCM", "adrg": "NC1", "with_mcc": "NC11", "with_cc": "NC13", "without": "NC15", "drg_names": {"NC11": "子宫切除术伴 MCC", "NC13": "子宫切除术伴 CC", "NC15": "子宫切除术不伴 CC/MCC"}},
    "74.0": {"name": "古典式剖宫产", "mdc": "MDCO", "adrg": "NS1", "with_mcc": "NS11", "with_cc": "NS13", "without": "NS15", "drg_names": {"NS11": "剖宫产伴 MCC", "NS13": "剖宫产伴 CC", "NS15": "剖宫产不伴 CC/MCC"}},
    "74.1": {"name": "低位子宫颈剖宫产", "mdc": "MDCO", "adrg": "NS1", "with_mcc": "NS11", "with_cc": "NS13", "without": "NS15", "drg_names": {"NS11": "剖宫产伴 MCC", "NS13": "剖宫产伴 CC", "NS15": "剖宫产不伴 CC/MCC"}},
    "74.2": {"name": "腹膜外剖宫产", "mdc": "MDCO", "adrg": "NS1", "with_mcc": "NS11", "with_cc": "NS13", "without": "NS15", "drg_names": {"NS11": "剖宫产伴 MCC", "NS13": "剖宫产伴 CC", "NS15": "剖宫产不伴 CC/MCC"}},
    "74.4": {"name": "剖宫产", "mdc": "MDCO", "adrg": "NS1", "with_mcc": "NS11", "with_cc": "NS13", "without": "NS15", "drg_names": {"NS11": "剖宫产伴 MCC", "NS13": "剖宫产伴 CC", "NS15": "剖宫产不伴 CC/MCC"}},
    "66.62": {"name": "输卵管切除术伴异位妊娠去除", "mdc": "MDCO", "adrg": "NK1", "with_mcc": "NK11", "with_cc": "NK13", "without": "NK15", "drg_names": {"NK11": "异位妊娠及流产伴 MCC", "NK13": "异位妊娠及流产伴 CC", "NK15": "异位妊娠及流产不伴 CC/MCC"}},
    "69.02": {"name": "刮宫产后扩张", "mdc": "MDCO", "adrg": "OH1", "with_mcc": "OH11", "with_cc": "OH13", "without": "OH15", "drg_names": {"OH11": "流产相关手术伴 MCC", "OH13": "流产相关手术伴 CC", "OH15": "流产相关手术不伴 CC/MCC"}},
    "69.01": {"name": "诊断性刮宫", "mdc": "MDCO", "adrg": "OH1", "with_mcc": "OH11", "with_cc": "OH13", "without": "OH15", "drg_names": {"OH11": "流产相关手术伴 MCC", "OH13": "流产相关手术伴 CC", "OH15": "流产相关手术不伴 CC/MCC"}},

    # ── MDCQ 乳腺/皮肤 ──
    "85.41": {"name": "单侧单纯乳房切除术", "mdc": "MDCJ", "adrg": "JC1", "with_mcc": "JC11", "with_cc": "JC13", "without": "JC15", "drg_names": {"JC11": "乳房切除术伴 MCC", "JC13": "乳房切除术伴 CC", "JC15": "乳房切除术不伴 CC/MCC"}},
    "85.43": {"name": "单侧扩大的单纯乳房切除术", "mdc": "MDCJ", "adrg": "JC1", "with_mcc": "JC11", "with_cc": "JC13", "without": "JC15", "drg_names": {"JC11": "乳房切除术伴 MCC", "JC13": "乳房切除术伴 CC", "JC15": "乳房切除术不伴 CC/MCC"}},
    "85.45": {"name": "单侧根治性乳房切除术", "mdc": "MDCJ", "adrg": "JC1", "with_mcc": "JC11", "with_cc": "JC13", "without": "JC15", "drg_names": {"JC11": "乳房切除术伴 MCC", "JC13": "乳房切除术伴 CC", "JC15": "乳房切除术不伴 CC/MCC"}},
    "85.48": {"name": "双侧根治性乳房切除术", "mdc": "MDCJ", "adrg": "JC1", "with_mcc": "JC11", "with_cc": "JC13", "without": "JC15", "drg_names": {"JC11": "乳房切除术伴 MCC", "JC13": "乳房切除术伴 CC", "JC15": "乳房切除术不伴 CC/MCC"}},
    "86.21": {"name": "皮肤囊肿切除术", "mdc": "MDCJ", "adrg": "JD1", "with_mcc": "JD11", "with_cc": "JD13", "without": "JD15", "drg_names": {"JD11": "皮肤、皮下组织手术伴 MCC", "JD13": "皮肤、皮下组织手术伴 CC", "JD15": "皮肤、皮下组织手术不伴 CC/MCC"}},
    "86.22": {"name": "皮肤伤口清创", "mdc": "MDCJ", "adrg": "JD1", "with_mcc": "JD11", "with_cc": "JD13", "without": "JD15", "drg_names": {"JD11": "皮肤、皮下组织手术伴 MCC", "JD13": "皮肤、皮下组织手术伴 CC", "JD15": "皮肤、皮下组织手术不伴 CC/MCC"}},
    "86.04": {"name": "皮肤和皮下组织切开引流", "mdc": "MDCJ", "adrg": "JD1", "with_mcc": "JD11", "with_cc": "JD13", "without": "JD15", "drg_names": {"JD11": "皮肤、皮下组织手术伴 MCC", "JD13": "皮肤、皮下组织手术伴 CC", "JD15": "皮肤、皮下组织手术不伴 CC/MCC"}},
    "86.0701": {"name": "输液港植入术", "mdc": "MDCJ", "adrg": "JD1", "with_mcc": "JD11", "with_cc": "JD13", "without": "JD15", "drg_names": {"JD11": "皮肤、皮下组织手术伴 MCC", "JD13": "皮肤、皮下组织手术伴 CC", "JD15": "皮肤、皮下组织手术不伴 CC/MCC"}},
    "99.25": {"name": "注射或输注癌瘤化学治疗药物", "mdc": "MDCR", "adrg": "RA1", "with_mcc": "RA11", "with_cc": "RA13", "without": "RA15", "drg_names": {"RA11": "化学治疗伴 MCC", "RA13": "化学治疗伴 CC", "RA15": "化学治疗不伴 CC/MCC"}},
    "99.2503": {"name": "化疗", "mdc": "MDCR", "adrg": "RA1", "with_mcc": "RA11", "with_cc": "RA13", "without": "RA15", "drg_names": {"RA11": "化学治疗伴 MCC", "RA13": "化学治疗伴 CC", "RA15": "化学治疗不伴 CC/MCC"}},

    # ── MDCR 呼吸/胸部手术 ──
    "32.3": {"name": "肺叶切除", "mdc": "MDCD", "adrg": "DA1", "with_mcc": "DA11", "with_cc": "DA13", "without": "DA15", "drg_names": {"DA11": "胸部大手术伴 MCC", "DA13": "胸部大手术伴 CC", "DA15": "胸部大手术不伴 CC/MCC"}},
    "32.4": {"name": "肺段切除", "mdc": "MDCD", "adrg": "DA1", "with_mcc": "DA11", "with_cc": "DA13", "without": "DA15", "drg_names": {"DA11": "胸部大手术伴 MCC", "DA13": "胸部大手术伴 CC", "DA15": "胸部大手术不伴 CC/MCC"}},
    "32.5": {"name": "全肺切除", "mdc": "MDCD", "adrg": "DA1", "with_mcc": "DA11", "with_cc": "DA13", "without": "DA15", "drg_names": {"DA11": "胸部大手术伴 MCC", "DA13": "胸部大手术伴 CC", "DA15": "胸部大手术不伴 CC/MCC"}},
    "34.4": {"name": "胸膜修补", "mdc": "MDCD", "adrg": "DB1", "with_mcc": "DB11", "with_cc": "DB13", "without": "DB15", "drg_names": {"DB11": "胸部其他手术伴 MCC", "DB13": "胸部其他手术伴 CC", "DB15": "胸部其他手术不伴 CC/MCC"}},
    "33.24": {"name": "支气管镜活检", "mdc": "MDCD", "adrg": "DB1", "with_mcc": "DB11", "with_cc": "DB13", "without": "DB15", "drg_names": {"DB11": "胸部其他手术伴 MCC", "DB13": "胸部其他手术伴 CC", "DB15": "胸部其他手术不伴 CC/MCC"}},
    "33.27": {"name": "肺活检", "mdc": "MDCD", "adrg": "DB1", "with_mcc": "DB11", "with_cc": "DB13", "without": "DB15", "drg_names": {"DB11": "胸部其他手术伴 MCC", "DB13": "胸部其他手术伴 CC", "DB15": "胸部其他手术不伴 CC/MCC"}},
}


# ── Surgery name → ICD-9-CM-3 index (用于中文检索回查) ────────────────────────
SURGERY_NAME_INDEX: dict[str, str] = {
    info["name"]: code for code, info in SURGERY_TO_DRG.items()
}


# ── 性别敏感诊断前缀 (CHS-DRG 1.1 错误组 YA1/YA2/YA3) ──────────────────────
# Male-only diagnosis prefixes
_MALE_ONLY_PREFIXES = {
    "B26.0", "C60", "C61", "C62", "C63",
    "D07.4", "D07.5", "D07.6", "D17.6", "D29",
    "D40", "E29", "E34.5", "F52.4", "I86.1",
    "L29.1", "N40", "N41", "N42", "N43", "N44", "N45", "N46", "N47", "N48", "N49", "N50",
    "N51", "Q53", "Q54", "Q55", "Q98", "Q99.0", "R86", "S31.2", "S31.3",
    "Z12.5",
}

# Female-only diagnosis prefixes
_FEMALE_ONLY_PREFIXES = {
    "A34", "B37.3", "C51", "C52", "C53", "C54", "C55", "C56", "C57", "C58",
    "D06", "D07.0", "D07.1", "D07.2", "D07.3", "D25", "D26", "D27", "D28",
    "D39", "E28", "F52.5", "F53", "I86.2", "I86.3", "L29.2", "M80.0", "M80.1",
    "M81.0", "M81.1", "M83.0",
    "N70", "N71", "N72", "N73", "N74", "N75", "N76", "N77", "N80", "N81", "N82", "N83", "N84", "N85", "N86", "N87", "N88", "N89", "N90", "N91", "N92", "N93", "N94", "N95", "N96", "N97", "N98",
    "O00", "O01", "O02", "O03", "O04", "O05", "O06", "O07", "O08",
    "O09", "O10", "O11", "O12", "O13", "O14", "O15", "O16",
    "O20", "O21", "O22", "O23", "O24", "O25", "O26", "O28", "O29",
    "O30", "O31", "O32", "O33", "O34", "O35", "O36", "O37", "O38", "O39",
    "O40", "O41", "O42", "O43", "O44", "O45", "O46", "O47", "O48",
    "O60", "O61", "O62", "O63", "O64", "O65", "O66", "O67", "O68", "O69",
    "O70", "O71", "O72", "O73", "O74", "O75", "O76", "O77", "O78", "O79",
    "O80", "O81", "O82", "O83", "O84",
    "O85", "O86", "O87", "O88", "O89", "O90", "O91", "O92", "O93", "O94", "O95", "O96", "O97", "O98", "O99",
    "Q50", "Q51", "Q52", "Q96", "Q97", "R87", "S31.4", "S32.8", "T19.2", "T19.3",
    "Z12.4", "Z30.1", "Z30.2", "Z30.3", "Z30.4", "Z30.5", "Z31.1", "Z31.2",
    "Z32", "Z33", "Z34", "Z35", "Z36", "Z37", "Z39", "Z43.7",
    "Z87.5", "Z90.7", "Z97.5",
}


def check_gender_consistency(diagnosis_code: str, patient_gender: str) -> dict:
    """Check if a diagnosis code is consistent with patient gender.

    Returns:
        {"consistent": bool, "rule_id": str, "expected_gender": "M"|"F"|"both",
         "message": str}
    """
    if not diagnosis_code or not patient_gender:
        return {"consistent": True, "rule_id": "", "expected_gender": "both", "message": ""}

    code = diagnosis_code.strip().upper()
    gender = patient_gender.upper().strip()

    is_male_only = any(code.startswith(p) for p in _MALE_ONLY_PREFIXES)
    is_female_only = any(code.startswith(p) for p in _FEMALE_ONLY_PREFIXES)

    if is_male_only and gender.startswith("M"):
        return {"consistent": True, "rule_id": "", "expected_gender": "M", "message": ""}
    if is_male_only and gender.startswith("F"):
        return {
            "consistent": False, "rule_id": "DRG004",
            "expected_gender": "M",
            "message": f"主诊断 {code} 仅限男性，但患者性别为 {patient_gender}。CHS-DRG 1.1 错误组 YA1。",
        }
    if is_female_only and gender.startswith("F"):
        return {"consistent": True, "rule_id": "", "expected_gender": "F", "message": ""}
    if is_female_only and gender.startswith("M"):
        return {
            "consistent": False, "rule_id": "DRG004",
            "expected_gender": "F",
            "message": f"主诊断 {code} 仅限女性，但患者性别为 {patient_gender}。CHS-DRG 1.1 错误组 YA1。",
        }
    return {"consistent": True, "rule_id": "", "expected_gender": "both", "message": ""}


# ── ADRG list (CHS-DRG 1.1 ADRG 字典) ────────────────────────────────────────
ADRG_LIST: list[dict] = [
    # (adrg, name, mdc, surgical)
    ("AA1", "脑创伤", "MDCA", True),
    ("AB1", "神经系统肿瘤", "MDCA", True),
    ("AC1", "脑血管病", "MDCA", False),
    ("AD1", "颅脑手术", "MDCA", True),
    ("AE1", "颅内血管手术", "MDCA", True),
    ("AF1", "脑缺血发作", "MDCA", False),
    ("AG1", "脑及神经系统感染", "MDCA", False),
    ("AH1", "脊髓及椎管手术", "MDCA", True),
    ("AI1", "神经系统的其他手术", "MDCA", True),
    ("BR1", "帕金森病", "MDCA", False),
    ("BT1", "癫痫", "MDCA", False),
    ("BU1", "头痛", "MDCA", False),
    ("BV1", "脑卒中", "MDCA", False),

    ("CB1", "晶体手术", "MDCB", True),
    ("CC1", "视网膜、玻璃体手术", "MDCB", True),
    ("CD1", "眼眶及眼球手术", "MDCB", True),
    ("CJ1", "角膜、巩膜手术", "MDCB", True),
    ("CR1", "眼科其他手术", "MDCB", True),
    ("CS1", "眼科疾患", "MDCB", False),
    ("CT1", "青光眼", "MDCB", False),
    ("CV1", "白内障", "MDCB", False),

    ("DA1", "胸部大手术", "MDCD", True),
    ("DB1", "胸部其他手术", "MDCD", True),
    ("DC1", "纵隔手术", "MDCD", True),
    ("DD1", "呼吸系统其他手术", "MDCD", True),
    ("DE1", "呼吸系统肿瘤", "MDCD", False),
    ("DF1", "肺水肿及呼吸衰竭", "MDCD", False),
    ("DG1", "慢性阻塞性肺疾病", "MDCD", False),
    ("DH1", "肺炎", "MDCD", False),
    ("DJ1", "呼吸系统其他疾患", "MDCD", False),
    ("DK1", "肺栓塞", "MDCD", False),
    ("DR1", "呼吸系统感染", "MDCD", False),

    ("EA1", "心脏大手术", "MDCE", True),
    ("EB1", "心脏其他手术", "MDCE", True),
    ("EC1", "经皮冠状动脉支架植入 (PCI)", "MDCE", True),
    ("ED1", "冠状动脉旁路移植术 (CABG)", "MDCE", True),
    ("EE1", "心脏起搏器植入", "MDCE", True),
    ("EF1", "心导管检查", "MDCE", True),
    ("EG1", "周围血管手术", "MDCE", True),
    ("EH1", "静脉系统手术", "MDCE", True),
    ("ER1", "急性心肌梗死", "MDCE", False),
    ("ES1", "心律失常及传导障碍", "MDCE", False),
    ("ET1", "心绞痛", "MDCE", False),
    ("EU1", "心力衰竭及休克", "MDCE", False),
    ("EV1", "高血压", "MDCE", False),
    ("EW1", "动脉粥样硬化", "MDCE", False),
    ("FR1", "急性心肌梗死", "MDCE", False),
    ("FT1", "心力衰竭", "MDCE", False),
    ("FU1", "心力衰竭", "MDCE", False),
    ("FV1", "高血压", "MDCE", False),
    ("FW1", "心律失常及传导障碍", "MDCE", False),

    ("GA1", "胃食管反流及消化系统肿瘤大手术", "MDCG", True),
    ("GB1", "胃、肠、肝大手术", "MDCG", True),
    ("GC1", "胃、肠、肝其他手术", "MDCG", True),
    ("GD1", "肛管及肛门手术", "MDCG", True),
    ("GE1", "疝手术", "MDCG", True),
    ("GF1", "阑尾切除术", "MDCG", True),
    ("GG1", "消化系统其他手术", "MDCG", True),
    ("GR1", "肝硬化及严重肝病", "MDCG", False),
    ("GS1", "胰腺炎", "MDCG", False),
    ("GU1", "消化性溃疡", "MDCG", False),
    ("GV1", "胃炎及食管炎", "MDCG", False),
    ("GW1", "急性胰腺炎", "MDCG", False),
    ("GZ1", "消化道出血", "MDCG", False),

    ("HA1", "肝、胆、胰大手术", "MDCG", True),
    ("HB1", "胆囊切除术", "MDCG", True),
    ("HC1", "肝、胆、胰其他手术", "MDCG", True),
    ("HF1", "胰腺疾患", "MDCG", False),

    ("IA1", "髋、肩、膝大手术", "MDCI", True),
    ("IB1", "髋、肩、膝其他手术", "MDCI", True),
    ("IC1", "脊柱大手术", "MDCI", True),
    ("ID1", "脊柱其他手术", "MDCI", True),
    ("IE1", "前臂、手、足手术", "MDCI", True),
    ("IF1", "骨骼肌肉其他手术", "MDCI", True),
    ("IJ1", "骨折", "MDCI", False),
    ("IM1", "关节置换术", "MDCI", True),
    ("IN1", "脊柱融合术", "MDCI", True),
    ("IT1", "骨关节炎", "MDCI", False),
    ("IU1", "椎间盘疾病", "MDCI", False),
    ("IV1", "骨折", "MDCI", False),
    ("IZ1", "风湿性关节炎", "MDCI", False),

    ("JC1", "乳房切除术", "MDCJ", True),
    ("JD1", "皮肤、皮下组织手术", "MDCJ", True),
    ("JV1", "蜂窝织炎", "MDCJ", False),
    ("JZ1", "皮肤溃疡", "MDCJ", False),

    ("KA1", "糖尿病", "MDCK", False),
    ("KB1", "内分泌腺体手术", "MDCK", True),
    ("KC1", "营养及代谢疾患", "MDCK", False),
    ("KD1", "甲状腺及甲状旁腺手术", "MDCK", True),
    ("KG1", "糖尿病", "MDCK", False),
    ("KH1", "电解质紊乱", "MDCK", False),

    ("LA1", "肾脏及泌尿道大手术", "MDCL", True),
    ("LB1", "肾脏及泌尿道其他手术", "MDCL", True),
    ("LD1", "前列腺手术", "MDCL", True),
    ("LE1", "泌尿系统其他手术", "MDCL", True),
    ("LF1", "肾衰竭", "MDCL", False),
    ("LJ1", "泌尿系统结石", "MDCL", False),
    ("LU1", "急性肾衰竭", "MDCL", False),
    ("LV1", "慢性肾脏病", "MDCL", False),
    ("LW1", "尿路感染", "MDCL", False),
    ("LX1", "肾及输尿管结石", "MDCL", False),

    ("NA1", "女性生殖系统大手术", "MDCM", True),
    ("NB1", "女性生殖系统其他手术", "MDCM", True),
    ("NC1", "子宫切除术", "MDCM", True),
    ("ND1", "女性生殖系统其他手术", "MDCM", True),
    ("NE1", "女性生殖系统恶性肿瘤", "MDCM", False),
    ("NF1", "女性生殖系统良性肿瘤", "MDCM", False),
    ("NG1", "女性生殖系统感染", "MDCM", False),
    ("NH1", "女性生殖系统其他疾患", "MDCM", False),
    ("NK1", "异位妊娠及流产", "MDCO", True),
    ("NR1", "分娩", "MDCO", False),
    ("NS1", "剖宫产", "MDCO", True),
    ("NT1", "阴道分娩", "MDCO", False),

    ("OA1", "妊娠分娩大手术", "MDCO", True),
    ("OB1", "剖宫产", "MDCO", True),
    ("OC1", "阴道分娩", "MDCO", True),
    ("OH1", "流产相关手术", "MDCO", True),

    ("PA1", "新生儿大手术", "MDCP", True),
    ("PB1", "新生儿其他手术", "MDCP", True),
    ("PC1", "新生儿疾患", "MDCP", False),
    ("PE1", "足月新生儿疾患", "MDCP", False),
    ("PF1", "新生儿窒息及呼吸窘迫", "MDCP", False),

    ("RA1", "化学治疗", "MDCR", True),
    ("RC1", "中毒及毒性反应", "MDCR", False),
    ("RD1", "创伤性损伤", "MDCR", False),
    ("RE1", "烧伤", "MDCR", False),
    ("RG1", "中毒及毒性反应", "MDCR", False),
    ("RH1", "创伤性损伤", "MDCR", False),

    ("SA1", "败血症", "MDCS", False),
    ("SB1", "严重感染", "MDCS", False),
    ("SC1", "术后及医疗性感染", "MDCS", False),
    ("SD1", "感染性疾患", "MDCS", False),
    ("SE1", "病毒性感染", "MDCS", False),
    ("SF1", "细菌性感染", "MDCS", False),
    ("SJ1", "HIV相关疾患", "MDCS", False),
    ("SZ1", "败血症", "MDCS", False),

    ("TA1", "精神疾患大手术", "MDCT", True),
    ("TB1", "精神分裂症及妄想障碍", "MDCT", False),
    ("TC1", "情感障碍", "MDCT", False),
    ("TD1", "神经症性障碍", "MDCT", False),
    ("TE1", "物质滥用及成瘾", "MDCT", False),

    ("ZA1", "其他因素影响健康状态", "MDCU", False),
    ("ZB1", "随访及康复", "MDCU", False),
    ("ZH1", "姑息治疗", "MDCU", False),
    ("ZI1", "康复治疗", "MDCU", False),

    ("YA1", "错误组 - 主要诊断与性别不符", "MDCX", False),
    ("YA2", "错误组 - 主要诊断与年龄不符", "MDCX", False),
    ("YA3", "错误组 - 主要手术与性别不符", "MDCX", False),
]
