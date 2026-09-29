import {expect,test} from 'vitest';
import {messagesFromTasks} from '../conversationHistory';
test('restores messages in task order and deduplicates shared history by identity',()=>{const message={messageId:'a',role:'user',parts:[{text:'Synthetic'}]};expect(messagesFromTasks([{history:[message]},{history:[message,{messageId:'b',role:'agent',parts:[{text:'Answer'}]}]}])).toEqual([{role:'user',content:'Synthetic'},{role:'assistant',content:'Answer'}]);});
test('preserves structured task outputs without inserting markup',()=>{expect(messagesFromTasks([{history:[],artifacts:[{parts:[{data:{status:'INPUT_REQUIRED'}}]}]}])[0].content).toContain('INPUT_REQUIRED');});
