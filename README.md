# youtube-local

![alt text](https://github.com/ndgsa/youtube-local/blob/master/screenshots/1.png?raw=true)

my fork with my local changes <br/>

* fork1 -> https://github.com/alive4ever/youtube-local/releases/tag/v2.8.12-playground01-pre <br/>
* innertube-client1 -> https://github.com/alive4ever/youtube-local/releases/tag/v2.8.12-playground13_feature-innertube-client-fix <br/>

Add my changes to alive4ever [fork](https://github.com/alive4ever/youtube-local). <br/>

My changes: <br/>
- Configure to load templates/ static/ data/ folder from assets/ folder. (assets/templates/ assets/static/ assets/data/) (Multiple forks and want to use common templates/ static/ data/) <br/>
- Add my version of dark theme. It can be enabled from settings. <br/>
- Add Home button menu. (mouse over Home button will show submenues) <br/>
- Added History page. (On video launch add video metadata to History playlist) <br/>
- Import and Export videos from/to playlist. (!!!Warning: This operation use too many requests to youtube. If want to import 50 or more videos to local playlist do them by chunks, becouse google can ban your ip.) <br/>
- Bookmark youtube playlist. <br/>
- Import youtube playlist to local playlist. (!!! Warning do not import playlist with too many videos, to not get ip ban. Instead export ids, divide them in different files and import one by one.) <br/>
- Hide videos/channels from related or search pages. (ammm Don't be surprised if no video on related or search page) <br/>
- Unhide videos/channels. (Go to hidden_videos_channels playlist and remove video/channel from them) <br/>
-  Search page now returns 60 results not 20 results. <br/>
- Channel page: add "Sort current page by views". <br/>
- Youtube playlist page: sort current playlist page by views, oldest, newest, title, author. <br/>
- Local playlist on watch page. <br/>
- Settings: Disable to add videos to history. <br/>
- Settings: Sort videos in playlist by recently added. <br/>
- Settings: Display local playlist videos as grid. <br/>
- Settings: Display youtube playlist videos as grid. <br/>
- Settings: Store images, playlist data in database (use sqlite3 database). If disabled will use files. <br/>

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
