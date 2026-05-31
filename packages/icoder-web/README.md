# @icoder/web

iCoDer Web Components — 可嵌入任何 HTML 页面的医疗 AI 组件。

零依赖，纯 Custom Elements API。

## 安装

```html
<script type="module">
  import '@icoder/web';
</script>
```

或

```bash
npm install @icoder/web
```

## 组件

### `<icoder-stt>` — 语音转录

```html
<icoder-stt language="zh-CN" placeholder="点击麦克风开始录音"></icoder-stt>
<script>
  const stt = document.querySelector('icoder-stt');
  stt.configure({ accessToken: '...', baseURL: 'http://localhost:8000' });
  stt.addEventListener('transcript', (e) => console.log(e.detail.text));
</script>
```

**属性**: `language`, `placeholder`
**方法**: `configure()`, `toggle()`, `clear()`, `getTranscript()`
**事件**: `transcript`, `error`

### `<icoder-assistant>` — AI 助手

```html
<icoder-assistant language="zh-CN"></icoder-assistant>
<script>
  const widget = document.querySelector('icoder-assistant');
  widget.configure({ accessToken: '...', baseURL: 'http://localhost:8000' });
</script>
```

**属性**: `language`, `mode`
**方法**: `configure()`
**事件**: 通过内建聊天 UI 交互

## License

MIT
