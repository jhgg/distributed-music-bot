import datetime
import functools
import youtube_dl

class ExtractedInfo(object):
    pass

async def extract_info(loop, url, *, ytdl_options=None, **kwargs):
    use_avconv = kwargs.get('use_avconv', False)
    opts = {
        'format': 'webm[abr>0]/bestaudio/best',
        'prefer_ffmpeg': not use_avconv
    }
    
    if ytdl_options is not None and isinstance(ytdl_options, dict):
        opts.update(ytdl_options)
    
    ydl = youtube_dl.YoutubeDL(opts)
    func = functools.partial(ydl.extract_info, url, download=False)
    info = await loop.run_in_executor(None, func)
    if "entries" in info:
        info = info['entries'][0]
    
    download_url = info['url']
    extracted_info = ExtractedInfo()
    
    # set the dynamic attributes from the info extraction
    extracted_info.download_url = download_url
    extracted_info.url = url
    extracted_info.yt = ydl
    extracted_info.views = info.get('view_count')
    extracted_info.is_live = bool(info.get('is_live'))
    extracted_info.likes = info.get('like_count')
    extracted_info.dislikes = info.get('dislike_count')
    extracted_info.duration = info.get('duration')
    extracted_info.uploader = info.get('uploader')
    
    is_twitch = 'twitch' in url
    if is_twitch:
        # twitch has 'title' and 'description' sort of mixed up.
        extracted_info.title = info.get('description')
        extracted_info.description = None
    else:
        extracted_info.title = info.get('title')
        extracted_info.description = info.get('description')
    
    # upload date handling
    date = info.get('upload_date')
    if date:
        try:
            date = datetime.datetime.strptime(date, '%Y%M%d').date()
        except ValueError:
            date = None
    
    extracted_info.upload_date = date
    return extracted_info
