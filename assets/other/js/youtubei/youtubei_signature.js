import { Innertube, Platform} from './youtubei.min.js'

// async function get_signature_data(){

  // let args;
  // let innertube;
  // let video_id;
  // let player_id;
  // let player_version;
  // let session_info;

  // if (typeof Deno !== 'undefined'){
    // args = Deno.args;
  // } else if (typeof Bun !== 'undefined'){
    // args = Bun.args;
  // } else {args = process.argv.slice(2);
  // };

  // if (args.length === 1){
    // video_id = args[0];
    // if (video_id.length != 11) {throw new Error('video_id is not valid');};
  // };
  // if (args.length === 2){
    // player_version = args[1];
    // if (player_version.length != 8) {throw new Error('player_version is not valid');};
  // };
  // if (args.length === 0){
    // throw new Error('Need at least one argument: identifier (video_id)');
  // };

  // Platform.shim.eval = async (data, env) => {
    // const properties = [];
    // if (env.n){properties.push(`n: exportedVars.nFunction("${env.n}")`);};
    // if (env.sig){properties.push(`sig: exportedVars.sigFunction("${env.sig}")`);};
    // const code = `${data.output}\nreturn { ${properties.join(', ')} }`;
    // session_info = {data};
    // return new Function(code)();
  // };

  // innertube = await Innertube.create({'client': 'TV', 'lang': 'en', 'retrieve_player': 'true', 'player_id': player_version});
  // var info = await innertube.getStreamingData(video_id, '');
  ////////// var player = innertube.session.player;
  // session_info.player_version = innertube.session.player.player_id;
  // console.log(JSON.stringify(session_info));
// };


(async function () {
  let args;
  let innertube;
  let player_version;

  if (typeof Deno !== 'undefined'){
    args = Deno.args;
  } else if (typeof Bun !== 'undefined'){
    args = Bun.args;
  } else {args = process.argv.slice(2);
  };

  try {
    if (args.length === 0){
      innertube = await Innertube.create({'client': 'TV', 'lang': 'en'});
      player_version = innertube.session.player.player_id;
    } else if (args.length === 1){
      player_version = args[0];
      if (player_version.length != 8){throw new Error('player_version is not valid');};
      innertube = await Innertube.create({'client': 'TV', 'lang': 'en', 'retrieve_player': 'true', 'player_id': player_version});
    };

  } catch (innertube_error) {
    console.error(innertube_error);
    return;
  };

  const session_info = {};
  session_info.data = innertube.session.player.data;
  session_info.player_version = player_version;
  console.log(JSON.stringify(session_info));
})();

  // session_info  -> [ 'output', 'exported', 'exportedRawValues' ]
  // session_info.output  -> It exports function text
  // session_info.exported -> [ 'sigFunction', 'nFunction', 'rawValues' ]
  // session_info.exportedRawValues -> {
                              // sigFunction: 'qv(1,decodeURIComponent(F))',
                              // nFunction: 'MjT',
                              // signatureTimestampVar: '20394'
                            // }

