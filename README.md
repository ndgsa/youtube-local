# youtube-local

![alt text](https://github.com/ndgsa/youtube-local/blob/master/screenshots/1.png?raw=true)

my fork with my local changes <br/>

* fork1 -> https://github.com/alive4ever/youtube-local/releases/tag/v2.8.12-playground01-pre <br/>
* innertube-client1 -> https://github.com/alive4ever/youtube-local/releases/tag/v2.8.12-playground14_feature-my-local-changes <br/>

Add my changes to alive4ever [fork](https://github.com/alive4ever/youtube-local). <br/>

My changes: <br/>
- Custom dark theme. <br/>
- Watch History page. <br/>
- Hide/Unhide videos/channels from related or search page. <br/>
- Bookmark youtube playlist. <br/>
- Search page returns 60 results not 20 results. <br/>
- Channel page: add "Sort current page by views". <br/>
- Youtube playlist page: sort current playlist page by views, oldest, newest, title, author. <br/>
- Local playlist displayed on watch page. <br/>
- Import/Export videos from/to playlist. (!!!Warning: Import maximum 50 videos per time. This operation uses too many requests to youtube, and google can ban your ip. ) <br/>
- Import youtube playlist to local playlist. (!!!Warning: Import maximum 50 videos per time. This operation uses too many requests to youtube, and google can ban your ip. ) <br/>
- Settings: Disable to add videos to history. <br/>
- Settings: Sort videos in playlist by recently added. <br/>
- Settings: Display local playlist videos as grid. <br/>
- Settings: Display youtube playlist videos as grid. <br/>
- Settings: Store images, playlist data in database (use sqlite3 database). If disabled will use files. <br/>
- Load templates, static, data folders from ./assets/ (assets/templates/ assets/static/ assets/data/). Comfortable if use multiple forks with common templates, data, static. <br/>
- Export thumbnails and playlists from sqlite to txt and vice versa to "assets/data/export" folder. Before this operation make a backup of your assets/data/ folder. <br/>
    - Export from txt to sqlite3 access - http://127.0.0.1:8080/youtube.com/export_from_txt_to_sqlite3 <br/>
    - Export from sqlite3 to txt access - http://127.0.0.1:8080/youtube.com/export_from_sqlite3_to_txt <br/>

There can be bugs bugs bugs. <br/>

<h3>I dont know how to fix if player stops playing after 2 minutes.</h3>

[comment]: <> (<a href="url"><img src="https://github.com/ndgsa/youtube-local/blob/master/screenshots/1.png" align="left" height="70%" width="70%"></a>)

## Screenshots
[Youtube playlist page display items as grid. Sort, bookmark, import.](https://github.com/ndgsa/youtube-local/blob/master/screenshots/2.png?raw=true)

[History page.](https://github.com/ndgsa/youtube-local/blob/master/screenshots/3.png?raw=true)

[Search page. Hide video, channel.](https://github.com/ndgsa/youtube-local/blob/master/screenshots/4.png?raw=true)

[Settings page.](https://github.com/ndgsa/youtube-local/blob/master/screenshots/5.png?raw=true)

## 
Use violentmonkey or similar thing in your browser to redirect youtube urls to localhost:8080 <br/> 

##
This are only cosmetic changes. <br/>
If want to ask something: https://github.com/ndgsa/youtube-local/discussions <br/>
