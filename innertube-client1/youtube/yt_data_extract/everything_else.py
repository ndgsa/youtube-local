from .common import (get, multi_get, deep_get, multi_deep_get,
    liberal_update, conservative_update, remove_redirect, normalize_url,
    extract_str, extract_formatted_text, extract_int, extract_approx_int,
    extract_date, check_missing_keys, extract_item_info, extract_items,
    extract_response)
from youtube import proto

import re
import urllib
from math import ceil

def extract_channel_info(polymer_json, tab, continuation=False):
    response, err = extract_response(polymer_json)
    if err:
        return {'error': err}


    metadata = deep_get(response, 'metadata', 'channelMetadataRenderer',
        default={})
    if not metadata:
        metadata = deep_get(response, 'microformat', 'microformatDataRenderer',
            default={})

    # channel doesn't exist or was terminated
    # example terminated channel: https://www.youtube.com/channel/UCnKJeK_r90jDdIuzHXC0Org
    # metadata and microformat are not present for continuation requests
    if not metadata and not continuation:
        if response.get('alerts'):
            error_string = ' '.join(
                extract_str(deep_get(alert, 'alertRenderer', 'text'), default='')
                for alert in response['alerts']
            )
            if not error_string:
                error_string = 'Failed to extract error'
            return {'error': error_string}
        elif deep_get(response, 'responseContext', 'errors'):
            for error in response['responseContext']['errors'].get('error', []):
                if error.get('code') == 'INVALID_VALUE' and error.get('location') == 'browse_id':
                    return {'error': 'This channel does not exist'}
        return {'error': 'Failure getting metadata'}

    info = {'error': None}
    info['current_tab'] = tab

    info['approx_subscriber_count'] = extract_approx_int(deep_get(response,
        'header', 'c4TabbedHeaderRenderer', 'subscriberCountText'))

    # stuff from microformat (info given by youtube for first page on channel)
    info['short_description'] = metadata.get('description')
    if info['short_description'] and len(info['short_description']) > 730:
        info['short_description'] = info['short_description'][0:730] + '...'
    info['channel_name'] = metadata.get('title')
    info['avatar'] = normalize_url(multi_deep_get(metadata,
        ['avatar', 'thumbnails', 0, 'url'],
        ['thumbnail', 'thumbnails', 0, 'url'],
    ))
    channel_url = multi_get(metadata, 'urlCanonical', 'channelUrl')
    if channel_url:
        channel_id = get(channel_url.rstrip('/').split('/'), -1)
        info['channel_id'] = channel_id
    else:
        info['channel_id'] = metadata.get('externalId')
    if info['channel_id']:
        info['channel_url'] = 'https://www.youtube.com/channel/' + channel_id
    else:
        info['channel_url'] = None

    # get items
    info['items'] = []
    info['ctoken'] = None

    info['channel_available_tabs'] = []
    for t in multi_deep_get(response, ['contents', 'twoColumnBrowseResultsRenderer', 'tabs'], default=[]):
        if t.get('tabRenderer', {}).get('title'):
            info['channel_available_tabs'].append(t.get('tabRenderer', {}).get('title'))

    # empty channel
    #if 'contents' not in response and 'continuationContents' not in response:
    #    return info

    if tab in ('videos', 'shorts', 'streams', 'playlists', 'releases', 'albums', 'podcasts', 'courses', 'search'):
        tab_is_type, tab_is_selected = None, None
        for t in multi_deep_get(response, ['contents', 'twoColumnBrowseResultsRenderer', 'tabs'], default=[]):
            t_tab_is_type = t.get('tabRenderer', {}).get('title')
            t_tab_is_selected = t.get('tabRenderer', {}).get('selected')
            if t_tab_is_selected == True and t_tab_is_type:
                if t_tab_is_type == 'Live': tab_is_type = 'Streams'
                elif t_tab_is_type == 'Home': tab_is_type = 'Videos'
                else: tab_is_type = t_tab_is_type
                tab_is_selected = t_tab_is_selected
                break

        custom_type = multi_deep_get(response,['contents', 'twoColumnBrowseResultsRenderer', 'tabs', 0, 'tabRenderer', 'content', 'sectionListRenderer', 'contents', 0, 'itemSectionRenderer', 'contents', 0, 'shelfRenderer', 'title', 'runs', 0, 'text'])
        if tab in ['videos', 'shorts', 'streams'] and custom_type in ['Albums & Singles']:
            tab_is_type = 'Playlists'

        # use first if available
        # if tab_is_type == None and tab_is_selected == None:
            # tab_is_selected = multi_deep_get(response, ['contents', 'twoColumnBrowseResultsRenderer', 'tabs', 0, 'tabRenderer', 'selected'],) # True
            # tab_is_type = multi_deep_get(response, ['contents', 'twoColumnBrowseResultsRenderer', 'tabs', 0, 'tabRenderer', 'title'],) # Videos

        # case when playlist/shorts is only available tab
        if tab_is_type and tab != tab_is_type.lower():
            print(f"Warning: {tab} tab have different response tab name: {tab_is_type}")

        if tab == 'videos':
            if tab_is_type not in ['Videos', 'Home', None]: items, ctoken = [], None
            else: items, ctoken = extract_items(response)
        elif tab == 'shorts':
            if tab_is_type not in ['Shorts', None]: items, ctoken = [], None
            else: items, ctoken = extract_items(response)
        elif tab == 'streams':
            if tab_is_type not in ['Streams', 'Live', None]: items, ctoken = [], None
            elif tab_is_type in ['Streams', 'Live']: items, ctoken = extract_items(response, item_types={'videoRenderer', 'lockupViewModel'})
            else: items, ctoken = extract_items(response)
        elif tab == 'playlists':
            if multi_deep_get(response, ['continuationContents', 'itemSectionContinuation', 'contents', 0, 'shelfRenderer', 'title', 'runs', 0, 'text']) not in ['Videos', 'Shorts', 'Streams', 'Music videos', 'Popular videos']:
                if tab_is_type in ['Videos'] and tab_is_selected == True and custom_type not in ['Albums & Singles']:
                    if custom_type: print(f"'{custom_type}' is not playlist type")
                    items, ctoken = [], None
                else: items, ctoken = extract_items(response, item_types={'lockupViewModel'})
            else:
                items, ctoken = [], None
        elif tab == 'releases':
            items, ctoken = extract_items(response, item_types={'playlistRenderer'})
        elif tab in ['albums', 'podcasts', 'courses']:
            items, ctoken = extract_items(response, item_types={'playlistRenderer', 'lockupViewModel'})
        else: items, ctoken = extract_items(response)

        additional_info = {
            'author': info['channel_name'],
            'author_id': info['channel_id'],
            'author_url': info['channel_url'],
        }
        info['items'] = [extract_item_info(renderer, additional_info) for renderer in items]
        info['ctoken'] = ctoken
        if tab in ('search', 'playlists', 'releases', 'albums', 'podcasts', 'courses'):
            info['is_last_page'] = (ctoken is None)
    elif tab == 'about':
        # Latest type
        items, _ = extract_items(response, item_types={'aboutChannelRenderer'})

        if not items:
            items = multi_deep_get(response, ['onResponseReceivedEndpoints', 0, 'showEngagementPanelEndpoint', 'engagementPanel', 'engagementPanelSectionListRenderer', 'content', 'sectionListRenderer', 'contents', 0, 'itemSectionRenderer', 'contents'], default=None)
            # also some info is here ['header', 'pageHeaderRenderer', 'content', 'pageHeaderViewModel', 'metadata', 'contentMetadataViewModel']
            # r_header = multi_deep_get(response, ['header', 'pageHeaderRenderer', 'content', 'pageHeaderViewModel', 'metadata', 'contentMetadataViewModel'], default=None)
            # info['approx_video_count'] = extract_approx_int(deep_get(r_header, 'metadataRows', 1, 'metadataParts', 1, 'text', 'content'))
            # info['approx_subscriber_count'] = extract_approx_int(deep_get(r_header, 'metadataRows', 1, 'metadataParts', 0, 'text', 'content'))
            # info['canonical_url'] = 'https://www.youtube.com/' + extract_str(deep_get(r_header, 'metadataRows', 0, 'metadataParts', 0, 'text', 'content', ))

        if items:
            a_metadata = deep_get(items, 0, 'aboutChannelRenderer',
                'metadata', 'aboutChannelViewModel')
            if not a_metadata:
                info['error'] = 'Could not find aboutChannelViewModel'
                return info

            info['links'] = []
            for link_outer in a_metadata.get('links', ()):
                link = link_outer.get('channelExternalLinkViewModel') or {}
                link_content = extract_str(deep_get(link, 'link', 'content'))
                for run in deep_get(link, 'link', 'commandRuns') or ():
                    url = remove_redirect(deep_get(run, 'onTap',
                        'innertubeCommand', 'urlEndpoint', 'url'))
                    if url and not (url.startswith('http://')
                            or url.startswith('https://')):
                        url = 'https://' + url
                    if link_content is None or (link_content in url):
                        break
                else: # didn't break
                    url = link_content
                    if url and not (url.startswith('http://')
                            or url.startswith('https://')):
                        url = 'https://' + url
                text = extract_str(deep_get(link, 'title', 'content'))
                info['links'].append( (text, url) )

            info['date_joined'] = extract_date(deep_get(a_metadata, 'joinedDateText', 'content'))
            info['view_count'] = extract_int(a_metadata.get('viewCountText'))
            info['approx_view_count'] = extract_approx_int(
                a_metadata.get('viewCountText')
            )
            info['description'] = extract_str(
                a_metadata.get('description'), default=''
            )
            info['approx_video_count'] = extract_approx_int(
                a_metadata.get('videoCountText')
            )
            info['approx_subscriber_count'] = extract_approx_int(
                a_metadata.get('subscriberCountText')
            )
            info['country'] = extract_str(a_metadata.get('country'))
            info['canonical_url'] = extract_str(
                a_metadata.get('canonicalChannelUrl')
            )

            if not info['short_description']:
                info['short_description'] = info['description']
                if info['short_description'] and len(info['short_description']) > 730:
                    info['short_description'] = info['short_description'][0:730] + '...'
            # if not info['channel_name']: info['channel_name'] = info['canonical_url'].replace("http://www.youtube.com/", "")
            if not info['channel_id']: info['channel_id'] = a_metadata.get('channelId')
            if not info['channel_url']: info['channel_url'] = 'https://www.youtube.com/channel/' + a_metadata.get('channelId')

        # Old type
        else:
            items, _ = extract_items(response,
                item_types={'channelAboutFullMetadataRenderer'})
            if not items:
                info['error'] = 'Could not find aboutChannelRenderer or channelAboutFullMetadataRenderer'
                return info
            a_metadata = items[0]['channelAboutFullMetadataRenderer']

            info['links'] = []
            for link_json in a_metadata.get('primaryLinks', ()):
                url = remove_redirect(deep_get(link_json, 'navigationEndpoint',
                    'urlEndpoint', 'url'))
                if url and not (url.startswith('http://')
                                or url.startswith('https://')):
                    url = 'https://' + url
                text = extract_str(link_json.get('title'))
                info['links'].append( (text, url) )

            info['date_joined'] = extract_date(a_metadata.get('joinedDateText'))
            info['view_count'] = extract_int(a_metadata.get('viewCountText'))
            info['description'] = extract_str(a_metadata.get(
                'description'), default='')

            info['approx_video_count'] = None
            info['approx_subscriber_count'] = None
            info['country'] = None
            info['canonical_url'] = None
    else:
        raise NotImplementedError('Unknown or unsupported channel tab: ' + tab)

    # check_for_empty_value('extract_channel_info', info, ['error', 'items', 'links', 'avatar', 'ctoken'])

    return info

def extract_search_info(polymer_json):
    response, err = extract_response(polymer_json)
    if err:
        return {'error': err}
    info = {'error': None}
    info['estimated_results'] = int(response['estimatedResults'])
    info['estimated_pages'] = ceil(info['estimated_results']/20)


    results, ctoken = extract_items(response)
    # ctoken = multi_deep_get(response, ['contents', 'twoColumnSearchResultsRenderer', 'primaryContents', 'sectionListRenderer', 'contents', 1, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'])
    info['ctoken'] = ctoken

    info['items'] = []
    info['corrections'] = {'type': None}
    for renderer in results:
        type = list(renderer.keys())[0]
        if type == 'shelfRenderer':
            continue
        if type == 'didYouMeanRenderer':
            renderer = renderer[type]

            info['corrections'] = {
                'type': 'did_you_mean',
                'corrected_query': renderer['correctedQueryEndpoint']['searchEndpoint']['query'],
                'corrected_query_text': renderer['correctedQuery']['runs'],
            }
            continue
        if type == 'showingResultsForRenderer':
            renderer = renderer[type]

            info['corrections'] = {
                'type': 'showing_results_for',
                'corrected_query_text': renderer['correctedQuery']['runs'],
                'original_query_text': renderer['originalQuery']['simpleText'],
            }
            continue

        i_info = extract_item_info(renderer)
        if i_info.get('type') != 'unsupported':
            info['items'].append(i_info)

    # refinement_filters
    info['search_refinement_filters'] = {}
    chips = multi_deep_get(polymer_json,
        ['response', 'header', 'searchHeaderRenderer', 'chipBar', 'chipCloudRenderer', 'chips'],
        # ['onResponseReceivedCommands', 1, 'reloadContinuationItemsCommand', 'continuationItems', 0, 'searchHeaderRenderer', 'chipBar', 'chipCloudRenderer', 'chips'],
        default=[])
    for c in chips:
        c_text = multi_deep_get(c, ['chipCloudChipRenderer', 'text', 'simpleText'])
        c_tok = multi_deep_get(c, ['chipCloudChipRenderer', 'navigationEndpoint', 'continuationCommand', 'token'])
        if c_text and c_tok:
            if c_text == 'All': continue
            info['search_refinement_filters'][c_text] = c_tok

    # check_for_empty_value('extract_search_info', info, ['error'])
    # check_for_empty_value('extract_search_info', info['items'], ['error', 'description', 'badges', 'index', 'video_count'])

    return info

def extract_search_refinement_info(polymer_json):
    if isinstance(polymer_json, dict) and ('onResponseReceivedCommands' in polymer_json or 'response' in polymer_json or 'responseContext' in polymer_json):
        response = polymer_json
    else:
        return {'error': 'Failed to extract response'}

    info = {'error': None}
    info['estimated_results'] = int(response['estimatedResults'])
    info['estimated_pages'] = ceil(info['estimated_results']/20)
    info['items'] = []
    info['corrections'] = {'type': None}
    info['search_refinement_filters'] = {}

    if 'onResponseReceivedCommands' in response:
        results = multi_deep_get(response,
        ['onResponseReceivedCommands', 0, 'reloadContinuationItemsCommand', 'continuationItems', 0, 'twoColumnSearchResultsRenderer', 'primaryContents', 'sectionListRenderer', 'contents', 0, 'itemSectionRenderer', 'contents'],
        ['onResponseReceivedCommands', 0, 'appendContinuationItemsAction', 'continuationItems', 0, 'itemSectionRenderer', 'contents'],
        default=[])
        for renderer in results:
            if 'gridShelfViewModel' in renderer:
                # for r1 in renderer['gridShelfViewModel']['contents']: info['items'].append(extract_item_info(r1))
                pass
            else:
                i_info = extract_item_info(renderer)
                if i_info.get('type') != 'unsupported':
                    info['items'].append(i_info)

    # refinement_filters
    chips = multi_deep_get(response,
        ['response', 'header', 'searchHeaderRenderer', 'chipBar', 'chipCloudRenderer', 'chips'],
        # ['onResponseReceivedCommands', 1, 'reloadContinuationItemsCommand', 'continuationItems', 0, 'searchHeaderRenderer', 'chipBar', 'chipCloudRenderer', 'chips'],
        default=[])
    for c in chips:
        c_text = multi_deep_get(c, ['chipCloudChipRenderer', 'text', 'simpleText'])
        c_tok = multi_deep_get(c, ['chipCloudChipRenderer', 'navigationEndpoint', 'continuationCommand', 'token'])
        if c_text and c_tok:
            if c_text == 'All': continue
            info['search_refinement_filters'][c_text] = c_tok

    ctoken = multi_deep_get(response,
        ['onResponseReceivedCommands', 0, 'reloadContinuationItemsCommand', 'continuationItems', 0, 'twoColumnSearchResultsRenderer', 'primaryContents', 'sectionListRenderer', 'contents', 1, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],
        ['onResponseReceivedCommands', 0, 'appendContinuationItemsAction', 'continuationItems', 1, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],
    )

    info['ctoken'] = ctoken

    return info

def extract_playlist_metadata(polymer_json):
    response, err = extract_response(polymer_json)
    if err:
        return {'error': err}

    metadata = {'error': None}
    header = deep_get(response, 'header', 'playlistHeaderRenderer', default={})
    metadata['title'] = extract_str(header.get('title'))

    metadata['first_video_id'] = deep_get(header, 'playEndpoint', 'watchEndpoint', 'videoId')
    first_id = re.search(r'([a-z_\-]{11})', deep_get(header,
        'thumbnail', 'thumbnails', 0, 'url', default=''))
    if first_id:
        conservative_update(metadata, 'first_video_id', first_id.group(1))
    if metadata['first_video_id'] is None:
        metadata['thumbnail'] = None
    else:
        metadata['thumbnail'] = 'https://i.ytimg.com/vi/' + metadata['first_video_id'] + '/mqdefault.jpg'

    metadata['video_count'] = extract_int(header.get('numVideosText'))
    metadata['description'] = extract_str(header.get('descriptionText'), default='')
    metadata['author'] = extract_str(header.get('ownerText'))
    metadata['author_id'] = multi_deep_get(header,
        ['ownerText', 'runs', 0, 'navigationEndpoint', 'browseEndpoint', 'browseId'],
        ['ownerEndpoint', 'browseEndpoint', 'browseId'])
    if metadata['author_id']:
        metadata['author_url'] = 'https://www.youtube.com/channel/' + metadata['author_id']
    else:
        metadata['author_url'] = None
    metadata['view_count'] = extract_int(header.get('viewCountText'))
    metadata['like_count'] = extract_int(header.get('likesCountWithoutLikeText'))
    for stat in header.get('stats', ()):
        text = extract_str(stat)
        if 'videos' in text:
            conservative_update(metadata, 'video_count', extract_int(text))
        elif 'views' in text:
            conservative_update(metadata, 'view_count', extract_int(text))
        elif 'updated' in text:
            metadata['time_published'] = extract_date(text)

    microformat = deep_get(response, 'microformat', 'microformatDataRenderer',
                           default={})
    conservative_update(
        metadata, 'title', extract_str(microformat.get('title'))
    )
    conservative_update(
        metadata, 'description', extract_str(microformat.get('description'))
    )
    conservative_update(
        metadata, 'thumbnail', deep_get(microformat, 'thumbnail',
                                        'thumbnails', -1, 'url')
    )


    header = multi_deep_get(response,
    ['header', 'pageHeaderRenderer', 'content', 'pageHeaderViewModel'],
    ['header', 'playlistHeaderRenderer'],
    ['sidebar', 'playlistSidebarRenderer', 'items', 0, 'playlistSidebarPrimaryInfoRenderer'],
    default={})

    metadata['first_video_id'] = multi_deep_get(header,
    ['playEndpoint', 'watchEndpoint', 'videoId'],
    ['playlistHeaderBanner', 'heroPlaylistThumbnailRenderer', 'onTap', 'watchEndpoint', 'videoId'],
    ['actions', 'flexibleActionsViewModel', 'actionsRows', 0, 'actions', 0,'buttonViewModel', 'onTap', 'innertubeCommand', 'watchEndpoint', 'videoId'],
    ['navigationEndpoint', 'watchEndpoint', 'videoId'],
    default='')

    first_id = re.search(r'([A-Za-z0-9_\-]{11})', multi_deep_get(header,
    ['thumbnail', 'thumbnails', 0, 'url'],
    ['playlistHeaderBanner', 'heroPlaylistThumbnailRenderer', 'thumbnail', 'thumbnails', 0, 'url'],
    ['thumbnailRenderer', 'playlistVideoThumbnailRenderer', 'thumbnail', 'thumbnails', 0, 'url'],
    default=''))

    if first_id:
        conservative_update(metadata, 'first_video_id', first_id.group(1))
    if metadata['first_video_id'] is None:
        metadata['thumbnail'] = None
    else:
        metadata['thumbnail'] = 'https://i.ytimg.com/vi/' + metadata['first_video_id'] + '/mqdefault.jpg'

    microformat = multi_deep_get(response, ['microformat', 'microformatDataRenderer'], default={})
    metadata['title'] = extract_str(microformat.get('title'))
    metadata['description'] = extract_str(microformat.get('description'))
    metadata['thumbnail'] = deep_get(microformat, 'thumbnail', 'thumbnails', -1, 'url')

    playlistSSIR = multi_deep_get(response,
    ['sidebar','playlistSidebarRenderer','items',1,'playlistSidebarSecondaryInfoRenderer'],
    ['contents', 'singleColumnBrowseResultsRenderer', 'tabs', 0, 'tabRenderer', 'content', 'sectionListRenderer', 'contents', 0, 'itemSectionRenderer', 'contents', 0, 'playlistVideoListRenderer', 'contents', 0, 'playlistVideoRenderer', 'shortBylineText'],
    default={})
    metadata['author'] = multi_deep_get(playlistSSIR,
    ['videoOwner','videoOwnerRenderer','title', 'runs', 0, 'text'],
    ['runs', 0, 'text'])
    metadata['author_id'] = multi_deep_get(playlistSSIR,
    ['videoOwner','videoOwnerRenderer', 'title', 'runs', 0, 'navigationEndpoint', 'browseEndpoint', 'browseId'],
    ['runs', 0, 'navigationEndpoint', 'browseEndpoint', 'browseId'])

    if metadata['author_id']:
        metadata['author_url'] = 'https://www.youtube.com/channel/' + metadata['author_id']
    else:
        metadata['author_url'] = None

    metadata['video_count'] = extract_int(multi_deep_get(header, ['numVideosText']))
    if not metadata['video_count']:
        metadata['video_count'] = extract_int(multi_deep_get(header, ['metadata', 'contentMetadataViewModel', 'metadataRows', 1, 'metadataParts', 1, 'text', 'content'], default='').replace(' videos','').replace(' episodes', ''))

    if not metadata['video_count']:
        metadata['video_count'] = extract_int("".join([i['text'] for i in multi_deep_get(header, ['stats', 0, 'runs'], default=[])]).replace(' videos','').replace(' episodes', ''))

    if not metadata['video_count']:
        metadata['video_count'] = extract_int("".join([i['text'] for i in multi_deep_get(response, ['sidebar', 'playlistSidebarRenderer', 'items', 0, 'playlistSidebarPrimaryInfoRenderer', 'stats', 0, 'runs'], default=[])]).replace(' videos','').replace(' episodes', ''))

    metadata['view_count'] = extract_int(multi_deep_get(header,['stats', 1, 'simpleText']))
    if not metadata['view_count']:
        for part in multi_deep_get(header, ['metadata','contentMetadataViewModel','metadataRows', -1, 'metadataParts'], default=[]):
            text = part.get('text', {}).get('content', '')
            if 'no views' in text.lower(): metadata['view_count'] = "0"
            elif 'view' in text.lower(): metadata['view_count'] = extract_int(text)
    if not metadata['view_count']:
        for part in multi_deep_get(response, ['sidebar', 'playlistSidebarRenderer', 'items', 0, 'playlistSidebarPrimaryInfoRenderer', 'stats'], default=[]):
            text = part.get('simpleText', '')
            if 'view' in text.lower(): metadata['view_count'] = extract_int(text)

    try:
        time_published1 = multi_deep_get(header, ['stats', -1, 'runs'], default=[])
        if not time_published1:
            time_published1 = multi_deep_get(response, ['sidebar', 'playlistSidebarRenderer', 'items', 0, 'playlistSidebarPrimaryInfoRenderer', 'stats', -1, 'runs'], default=[])

        if len(time_published1) == 1:
            from time import strftime
            if 'today' in time_published1[-1]['text'].lower():
                time_published1[0]['text'] = strftime("%b %d, %Y")
            elif 'yesterday' in time_published1[-1]['text'].lower():
                time_published1[0]['text'] = strftime("%b %d, %Y")
            elif is_date_matching(time_published1[-1].get('text', ''), '%b %d, %Y'): pass
            else: print('Not implemented date string', time_published1)

        metadata['time_published'] = extract_date(time_published1[-1]['text'])
    except:
        pass

    #print(response['sidebar']['playlistSidebarRenderer']['items'][0]['playlistSidebarPrimaryInfoRenderer'])
    #print(response['sidebar']['playlistSidebarRenderer']['items'][1]['playlistSidebarSecondaryInfoRenderer'])

    # check_for_empty_value('extract_playlist_metadata', metadata, ['error', 'description', 'like_count', 'view_count', 'time_published'])

    return metadata

def extract_playlist_info(polymer_json):
    response, err = extract_response(polymer_json)
    if err:
        return {'error': err}
    info = {'error': None}
    video_list, _ = extract_items(response)
    info['items'] = [extract_item_info(renderer) for renderer in video_list]

    info['metadata'] = extract_playlist_metadata(polymer_json)

    return info

def num_videos_from_uploads_playlist_info(pl_info):
    number_of_videos = None
    if pl_info['error'] and 'playlist does not exist' in pl_info['error']:
        return 0
    number_of_videos = deep_get(pl_info, 'metadata', 'video_count')
    if number_of_videos is None:
        print("Couldn't retrieve number of videos")
        if pl_info['error']:
            print(pl_info['error'])

    return number_of_videos

def _ctoken_metadata(ctoken):
    result = dict()
    params = proto.parse(proto.b64_to_bytes(ctoken))
    result['video_id'] = proto.parse(params[2])[2].decode('ascii')

    offset_information = proto.parse(params[6])
    result['offset'] = offset_information.get(5, 0)

    result['is_replies'] = False
    if (3 in offset_information) and (2 in proto.parse(offset_information[3])):
        result['is_replies'] = True
        result['sort'] = None
    else:
        try:
            result['sort'] = proto.parse(offset_information[4])[6]
        except KeyError:
            result['sort'] = 0
    return result

def extract_comments_info(polymer_json, ctoken=None):
    response, err = extract_response(polymer_json)
    if err:
        return {'error': err}
    info = {'error': None}

    if ctoken:
        metadata = _ctoken_metadata(ctoken)
    else:
        metadata = {}
    info['video_id'] = metadata.get('video_id')
    info['offset'] = metadata.get('offset')
    info['is_replies'] = metadata.get('is_replies')
    info['sort'] = metadata.get('sort')
    info['video_title'] = None

    comments, ctoken = extract_items(response,
        item_types={'commentThreadRenderer', 'commentRenderer'})
    info['comments'] = []
    info['ctoken'] = ctoken
    for comment in comments:
        comment_info = {}

        if 'commentThreadRenderer' in comment:  # top level comments
            conservative_update(info, 'is_replies', False)
            comment_thread  = comment['commentThreadRenderer']
            info['video_title'] = extract_str(comment_thread.get('commentTargetTitle'))
            if 'replies' not in comment_thread:
                comment_info['reply_count'] = 0
                comment_info['reply_ctoken'] = None
            else:
                comment_info['reply_count'] = extract_int(deep_get(comment_thread,
                    'replies', 'commentRepliesRenderer', 'moreText'
                ), default=1)   # With 1 reply, the text reads "View reply"
                comment_info['reply_ctoken'] = multi_deep_get(
                    comment_thread,
                    ['replies', 'commentRepliesRenderer', 'contents', 0,
                     'continuationItemRenderer', 'button', 'buttonRenderer',
                     'command', 'continuationCommand', 'token'],
                    ['replies', 'commentRepliesRenderer', 'continuations', 0,
                     'nextContinuationData', 'continuation']
                )
            comment_renderer = deep_get(comment_thread, 'comment', 'commentRenderer', default={})
        elif 'commentRenderer' in comment:  # replies
            comment_info['reply_count'] = 0     # replyCount, below, not present for replies even if the reply has further replies to it
            comment_info['reply_ctoken'] = None
            conservative_update(info, 'is_replies', True)
            comment_renderer = comment['commentRenderer']
        else:
            comment_renderer = {}

        # These 3 are sometimes absent, likely because the channel was deleted
        comment_info['author'] = extract_str(comment_renderer.get('authorText'))
        comment_info['author_url'] = normalize_url(deep_get(comment_renderer,
            'authorEndpoint', 'commandMetadata', 'webCommandMetadata', 'url'))
        comment_info['author_id'] = deep_get(comment_renderer,
            'authorEndpoint', 'browseEndpoint', 'browseId')

        comment_info['author_avatar'] = normalize_url(deep_get(
            comment_renderer, 'authorThumbnail', 'thumbnails', 0, 'url'))
        comment_info['id'] = comment_renderer.get('commentId')
        comment_info['text'] = extract_formatted_text(comment_renderer.get('contentText'))
        comment_info['time_published'] = extract_str(comment_renderer.get('publishedTimeText'))
        comment_info['like_count'] = comment_renderer.get('likeCount')
        comment_info['approx_like_count'] = extract_approx_int(
            comment_renderer.get('voteCount'))
        liberal_update(comment_info, 'reply_count', comment_renderer.get('replyCount'))

        info['comments'].append(comment_info)

    # check_for_empty_value('extract_comments_info', info, ['error', 'video_title', 'ctoken'])
    # check_for_empty_value('extract_comments_info', info['comments'], ['error', 'like_count', 'approx_like_count', 'reply_ctoken'])

    return info


def is_date_matching(date_str, date_format):
    from datetime import datetime
    # import time
    try: return bool(datetime.strptime(date_str, date_format)) # bool(time.strptime(date_str, date_format))
    except ValueError: return False



def check_for_empty_value(method_name, data_iter, ignore_key):

    def if_dict(method_name, data_iter, ignore_key):
        for k_data,v_data in data_iter.items():
            if v_data in [None, "", [], {}, ()] and k_data not in ignore_key:
                print(f"{method_name} Warning: '{k_data}' has empty value")

    if isinstance(data_iter, dict):
        if_dict(method_name, data_iter, ignore_key)
    elif isinstance(data_iter, list):
        # if list of dicts
        for l in data_iter:
            if_dict(method_name, l, ignore_key)

