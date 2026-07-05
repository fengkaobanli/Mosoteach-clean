import requests
import os
import re


class QuizExporter:
    def __init__(self, token):
        self.__token = token
        self.__base_url = 'https://coreapi.mosoteach.cn'
        self.headers = {
            'Connection': 'close',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
            'Content-Type': 'application/json;charset=utf-8',
            'X-client-app-id': 'MTWEB',
            'X-client-version': '6.0.0',
            'X-security-type': 'SECURITY_TYPE_TOKEN',
            'X-token': self.__token,
            'Origin': 'https://www.mosoteach.cn',
            'Referer': 'https://www.mosoteach.cn/'
        }
    
    def get_quiz_activities(self, cc_id):
        url = f'{self.__base_url}/ccs/{cc_id}/activities?roleId=2'
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            return [a for a in response.json().get('activities', []) if a.get('type') == 'QUIZ']
        except Exception as e:
            print(f'获取活动列表失败: {e}')
            return []
    
    def get_topics(self, cc_id, act_id):
        url = f'{self.__base_url}/ccs/{cc_id}/quizzes/{act_id}/topics'
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            return response.json().get('topics', [])
        except Exception as e:
            print(f'获取题目失败: {e}')
            return []
    
    def clean_html(self, text):
        if not text:
            return ''
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        text = text.replace('&lt;', '<').replace('&gt;', '>')
        return re.sub(r'\s+', ' ', text).strip()
    
    def clean_subject(self, text):
        if not text:
            return ''
        text = re.sub(r'<span class="mceNonEditable fill">填空 \d+</span>', '______', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ')
        return re.sub(r'\s+', ' ', text).strip()
    
    def get_question_parts(self, question, index):
        type_map = {'SINGLE': '单选题', 'MULTI': '多选题', 'TF': '判断题', 'FILL': '填空题'}
        q_type = question.get('type', 'UNKNOWN')
        type_label = type_map.get(q_type, q_type)
        
        if q_type == 'FILL':
            subject = self.clean_subject(question.get('subject', ''))
        else:
            subject = self.clean_html(question.get('subject', ''))
        t = f"{index}. [{type_label}] {subject}"
        
        options = question.get('options', [])
        x = ""
        if options:
            opt_parts = []
            for opt in options:
                letter = chr(65 + opt.get('itemNo', 0))
                content = self.clean_html(opt.get('content', ''))
                opt_parts.append(f"{letter}.{content}")
            x = " ".join(opt_parts)
        
        answer = '未知'
        if q_type == 'TF':
            tf_answer = question.get('tfAnswer')
            if tf_answer:
                answer = '对' if tf_answer == 'T' else '错'
        elif q_type == 'FILL':
            fill_data = question.get('fill', {})
            alternatives = fill_data.get('blankAlternatives', [])
            if alternatives:
                blanks = []
                for alt in alternatives:
                    blanks.append('/'.join(alt.get('contents', [])))
                answer = '|'.join(blanks)
        else:
            answers = question.get('answers', [])
            if answers:
                answer = ''.join([chr(65 + int(a)) for a in answers])
        
        prefix = '参考答案：' if q_type in ['MULTI', 'FILL'] else '答案:'
        d = f"{prefix}{answer}"
        
        return {'t': t, 'x': x, 'd': d}
    
    def apply_format(self, parts, format_str):
        """
        格式说明：
        - t=题目 x=选项 d=答案 n=换行
        - 空格只是说明符，不影响结构
        - 实际格式由 t, x, d, n 决定
        - 相邻重复占位符自动去重
        
        示例：
        - "tnx xnd" -> 题目/选项/答案（三行）
        - "t x d" -> 题目 选项 答案（一行）
        - "tnxnd" -> 题目/选项/答案（三行）
        - "txnxd" -> 题目选项/选项答案（两行）
        """
        # 只保留 t, x, d, n
        clean = ''
        for char in format_str:
            if char in ['t', 'x', 'd', 'n']:
                clean += char
        
        # 按 n 分割成行
        line_patterns = clean.split('n')
        result_lines = []
        
        for pattern in line_patterns:
            if not pattern:
                continue
            
            # 提取占位符，去重相邻重复
            placeholders = []
            for char in pattern:
                if char in ['t', 'x', 'd']:
                    if not placeholders or placeholders[-1] != char:
                        placeholders.append(char)
            
            # 构建行
            line_parts = []
            for ph in placeholders:
                if parts[ph]:
                    line_parts.append(parts[ph])
            
            if line_parts:
                result_lines.append(' '.join(line_parts))
        
        return '\n'.join(result_lines)
    
    def format_question(self, question, index, format_str=None):
        parts = self.get_question_parts(question, index)
        
        if format_str:
            return self.apply_format(parts, format_str)
        else:
            # 默认格式：题目/选项/答案各一行
            lines = [parts['t']]
            if parts['x']:
                lines.append(parts['x'])
            lines.append(parts['d'])
            return '\n'.join(lines)
    
    def export_activity(self, cc_id, act_id, act_name, course_name, format_str=None, link_mode=False):
        topics = self.get_topics(cc_id, act_id)
        if not topics:
            print(f'  活动 "{act_name}" 没有题目')
            return None
        
        content = '\n\n'.join([self.format_question(q, i+1, format_str) for i, q in enumerate(topics)])
        
        safe_course = re.sub(r'[\\/:*?"<>|]', '_', course_name)
        safe_act = re.sub(r'[\\/:*?"<>|]', '_', act_name)
        output_dir = os.path.join('.', safe_course)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        single = len([t for t in topics if t.get('type') == 'SINGLE'])
        multi = len([t for t in topics if t.get('type') == 'MULTI'])
        tf = len([t for t in topics if t.get('type') == 'TF'])
        fill = len([t for t in topics if t.get('type') == 'FILL'])
        
        if link_mode:
            print(f'  [OK] {act_name} ({single}单选,{multi}多选,{tf}判断,{fill}填空)')
            return {'name': act_name, 'content': content}
        else:
            file_path = os.path.join(output_dir, f'{safe_act}.txt')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f'  [OK] {act_name} ({single}单选,{multi}多选,{tf}判断,{fill}填空) -> {safe_act}.txt')
            return {'name': act_name, 'content': content}
    
    def export_all_activities(self, cc_id, course_name, format_str=None, link_mode=False):
        activities = self.get_quiz_activities(cc_id)
        if not activities:
            print('没有找到测验活动')
            return
        
        print(f'\n找到 {len(activities)} 个测验活动\n')
        
        results = []
        for act in activities:
            result = self.export_activity(cc_id, act.get('id'), act.get('title', '未命名活动'), course_name, format_str, link_mode)
            if result:
                results.append(result)
        
        if link_mode and results:
            safe_course = re.sub(r'[\\/:*?"<>|]', '_', course_name)
            output_dir = os.path.join('.', safe_course)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            combined = []
            for r in results:
                combined.append(f"=== {r['name']} ===")
                combined.append(r['content'])
                combined.append('')
            
            file_path = os.path.join(output_dir, f'{safe_course}_全部题目.txt')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(combined))
            print(f'\n{"="*50}')
            print(f'已合并到: {safe_course}_全部题目.txt')
        
        print(f'\n{"="*50}')
        print(f'导出完成: {len(results)}/{len(activities)} 个活动')
    
    def export_selected_activities(self, cc_id, course_name, selected_indices, format_str=None, link_mode=False):
        activities = self.get_quiz_activities(cc_id)
        if not activities:
            print('没有找到测验活动')
            return
        
        print(f'\n开始导出选中的活动...\n')
        
        results = []
        for idx in selected_indices:
            if 0 <= idx < len(activities):
                act = activities[idx]
                result = self.export_activity(cc_id, act.get('id'), act.get('title', '未命名活动'), course_name, format_str, link_mode)
                if result:
                    results.append(result)
        
        if link_mode and results:
            safe_course = re.sub(r'[\\/:*?"<>|]', '_', course_name)
            output_dir = os.path.join('.', safe_course)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            combined = []
            for r in results:
                combined.append(f"=== {r['name']} ===")
                combined.append(r['content'])
                combined.append('')
            
            file_path = os.path.join(output_dir, f'{safe_course}_选中题目.txt')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(combined))
            print(f'\n{"="*50}')
            print(f'已合并到: {safe_course}_选中题目.txt')
        
        print(f'\n{"="*50}')
        print(f'导出完成: {len(results)} 个活动')


def parse_export_params(input_str):
    parts = input_str.strip().split()
    
    link_mode = False
    format_parts = []
    act_indices = []
    
    for part in parts:
        if part == '-link':
            link_mode = True
        elif part == 'all':
            act_indices = 'all'
        elif re.match(r'^\d+$', part):
            act_indices.append(int(part) - 1)
        else:
            format_parts.append(part)
    
    format_str = ' '.join(format_parts) if format_parts else None
    return act_indices, format_str, link_mode


def quiz_export_main(token, course_list_data):
    print('\n' + '='*50)
    print('题库导出功能')
    print('='*50)
    print('\n格式说明:')
    print('  t=题目 x=选项 d=答案 n=换行')
    print('  相邻重复占位符自动去重')
    print('  示例:')
    print('    tnx xnd  -> 题目/选项/答案（三行）')
    print('    t x d    -> 题目 选项 答案（一行）')
    print('    tnxnd    -> 题目/选项/答案（三行）')
    print('    txnxd    -> 题目选项/选项答案（两行）')
    print('  -link 参数: 将所有题目合并到一个文件')
    print('='*50)
    
    data = course_list_data
    for num, dat in enumerate(data, start=1):
        course_name = dat['course']['name']
        clazz_name = dat['clazz']['name']
        creater_name = dat.get('creater', {}).get('full_name', dat.get('creater', {}).get('fullName', '未知教师'))
        status = dat.get('status', 'OPEN')
        if status == 'CLOSED':
            print(f'{num} [已结束] {course_name} {clazz_name} {creater_name}')
        else:
            print(f'{num} {course_name} {clazz_name} {creater_name}')
    
    choice = input('\n请选择要导出题目的班课(多个用空格隔开, 全选输入all): ').strip()
    if not choice:
        print('没有选择!')
        return
    
    exporter = QuizExporter(token)
    
    if choice.upper() == 'ALL':
        for dat in data:
            if dat.get('status', 'OPEN') == 'CLOSED':
                continue
            cc_id = dat['id']
            course_name = dat['course']['name']
            
            print(f'\n{"="*50}')
            print(f'课程: {course_name}')
            print(f'{"="*50}')
            
            activities = exporter.get_quiz_activities(cc_id)
            if not activities:
                print('没有测验活动')
                continue
            
            print('\n测验活动列表:')
            for i, act in enumerate(activities, 1):
                print(f'{i}. {act.get("title", "未命名")} ({act.get("topicCount", 0)}题)')
            
            act_input = input('\n请输入导出参数 (all/编号 格式 -link): ').strip()
            if not act_input:
                continue
            
            act_indices, format_str, link_mode = parse_export_params(act_input)
            
            if act_indices == 'all':
                exporter.export_all_activities(cc_id, course_name, format_str, link_mode)
            elif isinstance(act_indices, list) and act_indices:
                exporter.export_selected_activities(cc_id, course_name, act_indices, format_str, link_mode)
            else:
                print('输入错误!')
    else:
        try:
            choices = sorted(list(set([int(x)-1 for x in choice.split()])))
            for idx in choices:
                if 0 <= idx < len(data):
                    dat = data[idx]
                    cc_id = dat['id']
                    course_name = dat['course']['name']
                    
                    print(f'\n{"="*50}')
                    print(f'课程: {course_name}')
                    print(f'{"="*50}')
                    
                    activities = exporter.get_quiz_activities(cc_id)
                    if not activities:
                        print('没有测验活动')
                        continue
                    
                    print('\n测验活动列表:')
                    for i, act in enumerate(activities, 1):
                        print(f'{i}. {act.get("title", "未命名")} ({act.get("topicCount", 0)}题)')
                    
                    act_input = input('\n请输入导出参数 (all/编号 格式 -link): ').strip()
                    if not act_input:
                        continue
                    
                    act_indices, format_str, link_mode = parse_export_params(act_input)
                    
                    if act_indices == 'all':
                        exporter.export_all_activities(cc_id, course_name, format_str, link_mode)
                    elif isinstance(act_indices, list) and act_indices:
                        exporter.export_selected_activities(cc_id, course_name, act_indices, format_str, link_mode)
                    else:
                        print('输入错误!')
        except:
            print('输入错误!')
