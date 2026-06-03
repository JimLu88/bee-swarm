# 📚 投书文件夹 books_dropzone

把你收集到的书放进**这个文件夹**(支持子文件夹任意分类),格式支持:
`.pdf .epub .mobi .azw3 .txt .docx .doc`

文件名尽量包含**书名**(可带作者),例如:
- `最好的告别-阿图葛文德.epub`
- `黄帝内经(王冰注本).pdf`
- `身体从未忘记.pdf`

## 每次加完书,跑一次扫描:
```bash
# 在 backend 目录下
python -m app.seed_knowledge.booklib_check
```
或指定别的文件夹:
```bash
python -m app.seed_knowledge.booklib_check --dropzone "D:\\我的书库"
```

扫描会对照 `app/seed_knowledge/booklists/*.md` 里所有书单,生成报告
`app/seed_knowledge/booklists/_inventory_report.md`,告诉你:
- ✅ **已到位已灌**(被程序使用)
- 📥 **已到位未灌**(书在,但还没进知识库)
- ❌ **缺失**(书单里要、文件夹里还没有)
- ❓ **多余文件**(文件夹里有、但不在任何书单)
