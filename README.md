# youtube-local



![alt text](https://github.com/ndgsa/youtube-local/blob/playground/screenshots/1.png?raw=true)

<br/>

### My fork with cosmetic changes + features from [alive4ever](https://github.com/alive4ever/youtube-local) and [yt-local](https://git.sr.ht/~heckyel/yt-local/) forks <br/>

<br/>

## No longer working:
 - YouTube API v1.0 deprecated
 - Subscriptions rss feed (partially)
 - Age-restricted videos unavailable
 - Filter by date api removed
 - ...

In near future (2026), this fork will be unusable. Youtube limits opportunities for unofficial software.

<br/>

## My changes: <br/>
- Custom dark theme. <br/>
- Local History page. <br/>
- Hide/Unhide videos/channels from related or search page. <br/>
- Bookmark youtube playlist. <br/>
- Search page returns 40 results not 20 results. <br/>
- Search/Channel/Playlist/Watch page: sort current page videos by views, oldest, newest, title, author. <br/>
- Local playlist displayed on watch page. <br/>
- Import videos to local playlist. (!!!Warning: Uses many requests to youtube, do not import big playlist.) <br/>
- Rename playlist on playlist edit page. (Click on the playlist title in the header.) <br/>
(Warning: If old playlist name contains invalid symbols and an error occurred, need to rename manually file/folder/db.)
- Reorder playlist videos on playlist edit page. <br/>
- Handle auto-dubbed audio tracks. Settings: disable_dubbing, allowed_dubbing_languages. <br/>
- Only portable mode. <br/>
- Settings: Sort videos in playlist by recently added. <br/>
- Settings: Store images, playlist data in sqlite3 database. If disabled will use files. <br/>
- Settings: Changed defaults. <br/>
- Export thumbnails and playlists from sqlite to txt and vice versa to `./youtube-local/data/export/` folder. Before this operation make a backup of your `./youtube-local/data/` folder . <br/>
    - Export from txt to sqlite3 access: `<localhost:port>/youtube.com/export_from_txt_to_sqlite3` <br/>
    - Export from sqlite3 to txt access: `<localhost:port>/youtube.com/export_from_sqlite3_to_txt` <br/>
- Some fixes.

## Javascript runtime
Some functions like `signature decryption`, `po_Token generation` - require javascript runtime like `node.js`. <br/>
For `windows 7` can use v20 [nodejs](https://github.com/vladimir-andreevich/node.js-windows-7).

## po_Token
Generation of `po_token` require `node.js` and [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider). <br/>
1. Go to [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider) repo and set up server.
2. Launch `bgutil-ytdlp-pot-provider` server.
3. In web browser access `youtube-local` 'settings' page and check `Use po_token` option.
4. Done.

Even if all requirements are installed, generation of `po_token` can fail. The only client that does not require `po_Token` is `android_vr`.

[comment]: <> (<a href="url"><img src="https://github.com/ndgsa/youtube-local/blob/playground/screenshots/1.png" align="left" height="70%" width="70%"></a>)

## Screenshots
[Youtube playlist page display items as grid. Sort, bookmark, import.](https://github.com/ndgsa/youtube-local/blob/playground/screenshots/2.png?raw=true)

[History page.](https://github.com/ndgsa/youtube-local/blob/playground/screenshots/3.png?raw=true)

[Search page. Hide video, channel.](https://github.com/ndgsa/youtube-local/blob/playground/screenshots/4.png?raw=true)

[Settings page. Home button submenu.](https://github.com/ndgsa/youtube-local/blob/playground/screenshots/5.png?raw=true)

## Warning! If use older versions please install new version on different path.
1. Migrate `data` folder from `./old-youtube-local/assets/data/` to `./youtube-local/data/`.
2. Also copy `settings.txt` from `./old-youtube-local/innertube-client1/` to `./youtube-local/`.

##
Use violentmonkey or similar to redirect youtube urls to localhost:8080 <br/>


##
If want to ask something: https://github.com/ndgsa/youtube-local/discussions <br/>
