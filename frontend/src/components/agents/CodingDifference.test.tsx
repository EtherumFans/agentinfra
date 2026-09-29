// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,test} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import CodingDifference from './CodingDifference';
afterEach(cleanup);
test('legacy evidence is explicitly unavailable, never fabricated',()=>{
 render(<CodingDifference checks={[{path:'primary_diagnosis_code',passed:false}]}/>);
 expect(screen.getByText(/此历史报告未保存编码对照数据/)).toBeTruthy();
});
test('shows exact code strings and diagnostic categories, toggles passed fields',()=>{
 render(<CodingDifference checks={[{path:'primary_diagnosis_code',passed:false,coding_comparison:{available:true,expected:['A01.001'],actual:['A01'],missing:['A01.001'],extra:['A01'],categories:['possible_extension']}},{path:'other_diagnosis_codes',passed:true,coding_comparison:{available:true,expected:[],actual:[],missing:[],extra:[],categories:[]}}]}/>);
 expect(screen.getByText('A01.001')).toBeTruthy();
 expect(screen.getByText('疑似扩展位差异')).toBeTruthy();
 expect(screen.queryByText('其他诊断')).toBeNull();
 fireEvent.click(screen.getByRole('checkbox'));
 expect(screen.getByText('其他诊断')).toBeTruthy();
});
