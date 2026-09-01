{
  "schema": "novel-studio.state-mutation/v2",
  "chapter": "{{slot:chapter_id|ch_001}}",
  "operation_id": "{{slot:chapter_id|ch_001}}.reader.{{slot:timestamp|0901_2000}}",
  "current": {
    "present_characters": [
      "{{slot:protagonist|主角名}}"
    ],
    "region": "{{slot:region|大地图宏观区域}}",
    "location": "{{slot:location|章末场景地点}}",
    "time": "{{slot:time|当前时辰或日期}}",
    "situation": "{{slot:situation|章末局势一句话速写}}"
  },
  "entities": [],
  "lines": [],
  "ledger": {
    "transactions": []
  },
  "timeline": {
    "events": [
      {
        "time": "{{slot:time|时间锚点}}",
        "event": "{{slot:event|核心剧情事件}}"
      }
    ],
    "arcs": [],
    "clocks": []
  },
  "synopsis": {
    "title": "{{slot:title|本章标题}}",
    "text": "{{slot:synopsis|本章核心剧情一句话梗概}}"
  }
}
