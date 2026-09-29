"""Bounded, non-persistent Excel preview. No model calls or answer leakage."""
from io import BytesIO
import re
from zipfile import ZipFile, BadZipFile
from openpyxl import load_workbook
from app.services.release_evaluation import EvaluationCase

TEXT_HEADERS=['主诉','现病史','既往史','个人史','婚姻史','家族史','入院情况','入院诊断','诊疗经过','出院情况','出院医嘱','手术经过','术前诊断','术中诊断']
LABELS={'主要疾病（诊断）编码':'primary_diagnosis_code','其他疾病（诊断）编码':'other_diagnosis_codes','主要手术编码':'primary_procedure_code','其他手术编码':'other_procedure_codes'}

# Preserve compound labels as one answer: '+' joins components, '*' is a suffix.
# This checks import syntax only, not validity against a medical coding dictionary.
CODE_LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9.\-]*\*?(?:\+[A-Za-z0-9][A-Za-z0-9.\-]*\*?)*')

def preview_training_xlsx(content:bytes,start:int=1,limit:int=10,maximum:int=10):
    if not 1<=start<=20000 or not 1<=limit<=maximum:raise ValueError('记录范围超出限制。')
    if len(content)>10*1024*1024:raise ValueError('Excel 文件不能超过 10 MB。')
    try:
        with ZipFile(BytesIO(content)) as z:
            files=z.infolist()
            if len(files)>2000 or sum(f.file_size for f in files)>64*1024*1024:raise ValueError('Excel 解压后超出大小限制。')
            if any('vbaproject' in f.filename.lower() or 'externallinks/' in f.filename.lower() for f in files):raise ValueError('不支持宏或外部链接，请导出纯数据工作簿。')
        wb=load_workbook(BytesIO(content),read_only=True,data_only=False,keep_links=False)
    except ValueError:
        raise ValueError('Excel 结构无效或超出限制，请使用不含宏和外部链接的纯数据 .xlsx 文件。') from None
    except Exception:
        raise ValueError('无法读取 Excel，请使用标准 .xlsx 文件。') from None
    try:
        matches=[]
        for sheet in wb.worksheets:
            header=[str(c.value).strip() if c.value is not None else '' for c in next(sheet.iter_rows(min_row=1,max_row=1,max_col=64),())]
            if set(LABELS).issubset(header) and any(h in header for h in TEXT_HEADERS):matches.append((sheet,header))
        if len(matches)!=1:raise ValueError('需要且只能有一个数据表包含四类编码列及病历正文列，列名请参照训练集格式说明。')
        sheet,header=matches[0]
        if any(header.count(h)>1 for h in (*TEXT_HEADERS,*LABELS)):raise ValueError('数据表存在重复列名。')
        total=max(0,(sheet.max_row or 1)-1)
        if start>total:raise ValueError('起始记录超出数据表范围。')
        index={h:i for i,h in enumerate(header) if h}
        cases=[];issues=[]
        for n,row in enumerate(sheet.iter_rows(min_row=start+1,max_row=min(start+limit-1,total)+1,max_col=len(header)),start=start):
            def value(h):
                if h not in index:return None
                cell=row[index[h]]
                if cell.data_type=='f':raise ValueError('所选记录含公式，请先粘贴为值。')
                return cell.value
            try:
                sections=[f'{h}：{value(h)}' for h in TEXT_HEADERS if value(h) is not None and str(value(h)).strip()]
                if not sections:raise ValueError('缺少病历正文。')
                expected={}
                for h,key in LABELS.items():
                    raw=value(h)
                    if raw is not None and not isinstance(raw,str):raise ValueError('编码列须为文本，以保留前导零。')
                    codes=[] if raw is None or raw.strip() in ('','无','无手术','未行手术','不适用') else [c.strip() for c in re.split(r'[;；、,，\n]+',raw) if c.strip()]
                    if any(not CODE_LABEL.fullmatch(c) for c in codes):raise ValueError('编码标签格式无法识别，请检查空值标记或分隔符。')
                    if key.startswith('primary_'):
                        if len(codes)>1:raise ValueError('主要编码列不能包含多个编码。')
                        expected[key]=codes[0] if codes else None
                    else:expected[key]=codes
                prompt='合成或脱敏编码评测。依据以下病历资料输出 JSON，字段 primary_diagnosis_code、primary_procedure_code 为主要编码字符串（没有则 null）；other_diagnosis_codes、other_procedure_codes 为其他编码字符串数组（没有则 []）。不要补造资料。\n'+'\n'.join(sections)
                case=EvaluationCase(id=f'row-{n:05d}',text=prompt,expected_json=expected)
                cases.append(case.model_dump(exclude_defaults=True))
            except ValueError as exc:
                # Pydantic errors may contain clinical input; expose fixed text only.
                message='正文或预期结果超出单条评测限制。' if hasattr(exc,'errors') else str(exc)
                issues.append({'record':n,'message':message})
        return {'cases':cases,'issues':issues,'total_rows':total,'start':start,'selected_count':min(limit,total-start+1),'format':'clinical-coding-xlsx/v1'}
    finally:wb.close()
