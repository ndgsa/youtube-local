# youtube-local



![alt text](https://github.com/ndgsa/youtube-local/blob/playground/screenshots/1.png?raw=true)

<br/>

### My fork with cosmetic changes + features from alive4ever [fork](https://github.com/alive4ever/youtube-local) <br/>

<br/>

## No longer working:
 - YouTube API v1.0 deprecated
 - Subscriptions rss feed (partially)
 - Age-restricted videos unavailable
 - Filter by date api removed
 - ...

In near future (2026), this fork will be unusable. Youtube changes too many things.

<br/>

## My changes: <br/>
- Custom dark theme. <br/>
- Watch History page. <br/>
- Hide/Unhide videos/channels from related or search page. <br/>
- Bookmark youtube playlist. <br/>
- Search page returns 60 results not 20 results. <br/>
- Channel page: "Sort current page by views". <br/>
- Youtube playlist page: sort current playlist page by views, oldest, newest, title, author. <br/>
- Local playlist displayed on watch page. <br/>
- Import videos to local playlist. (!!!Warning: This operation uses many requests to youtube, do not import big playlist.) <br/>
- Rename playlist on playlist edit page. (Click on the playlist title in the header.) <br/>
(Warning: If old playlist name contains invalid symbols and an error occurred, need to rename manually file/folder.)
- Reorder playlist videos on playlist edit page. <br/>
- Handle auto-dubbed audio tracks. Settings: disable_dubbing , allowed_dubbing_languages. <br/>
- Only portable mode. <br/>
- Settings: Sort videos in playlist by recently added. <br/>
- Settings: Store images, playlist data in sqlite3 database. If disabled will use files. <br/>
- Settings: Changed defaults. <br/>

- Export thumbnails and playlists from sqlite to txt and vice versa to `./youtube-local/data/export/` folder. Before this operation make a backup of your `./youtube-local/data/` folder . <br/>
    - Export from txt to sqlite3 access: http://127.0.0.1:8080/youtube.com/export_from_txt_to_sqlite3 <br/>
    - Export from sqlite3 to txt access: http://127.0.0.1:8080/youtube.com/export_from_sqlite3_to_txt <br/>
<br/>

- Some fixes.

## Javascript runtime - node.js
Some functions like signature decryption, po_Token generation, require node.js.

## po_Token
Generation of `po_token` require node.js and installed javascript packages. Even if all requirements are installed, generation does not work correctly for some reason. <br/>
The only client that does not require `po_Token` is `android_vr`. On Settings page find `Innertube client` and select `android_vr` client, then press button `Save settings` at the bottom of page.

[comment]: <> (<a href="url"><img src="https://github.com/ndgsa/youtube-local/blob/playground/screenshots/1.png" align="left" height="70%" width="70%"></a>)

## Screenshots
[Youtube playlist page display items as grid. Sort, bookmark, import.](https://github.com/ndgsa/youtube-local/blob/playground/screenshots/2.png?raw=true)

[History page.](https://github.com/ndgsa/youtube-local/blob/playground/screenshots/3.png?raw=true)

[Search page. Hide video, channel.](https://github.com/ndgsa/youtube-local/blob/playground/screenshots/4.png?raw=true)

[Settings page. Home button submenu.](https://github.com/ndgsa/youtube-local/blob/playground/screenshots/5.png?raw=true)

##

## Warning! Do not overwrite release with your youtube-local. Structures are different. <br/>


##
Use violentmonkey or similar to redirect youtube urls to localhost:8080 <br/>


##
If want to ask something: https://github.com/ndgsa/youtube-local/discussions <br/>
