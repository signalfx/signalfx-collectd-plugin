import getpass
import json
import urllib2
import argparse
import sys

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Helper script that gives you all the access tokens your account has.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--url', default='https://api.signalfuse.com', help='SignalFX endpoint')
    parser.add_argument('--password', default=None, help='Optional command line password')
    parser.add_argument('--org', default=None, help='If set, change output to only the auth token of this org')

    parser.add_argument('user_name', help="User name to log in with")

    args = parser.parse_args()
    if args.password is None:
        args.password = getpass.getpass('SignalFX password: ')

    # Get the session
    json_payload = {"email": args.user_name, "password":args.password}
    headers = {'content-type': 'application/json'}
    req = urllib2.Request(args.url + "/session", json.dumps(json_payload), headers)
    try:
        resp = urllib2.urlopen(req)
    except urllib2.HTTPError as e:
        sys.stderr.write("Invalid user name/password\n")
        sys.exit(1)
    res = resp.read()
    sf_accessToken = json.loads(res)['sf_accessToken']
    sf_userID = json.loads(res)['sf_userID']

    # Get the orgs
    orgs_url = args.url + "/orguser?query=sf_userID:%s" % sf_userID
    headers = {'content-type': 'application/json', 'X-SF-TOKEN': sf_accessToken}
    req = urllib2.Request(orgs_url, headers=headers)
    resp = urllib2.urlopen(req)
    res = resp.read()
    all_res = json.loads(res)
    printed_org = False
    for i in all_res['rs']:
        if args.org is not None:
            if args.org == i['sf_organization']:
                sys.stdout.write(i['sf_apiAccessToken'])
                printed_org = True
        else:
            print "%40s%40s" % (i['sf_organization'], i['sf_apiAccessToken'])
    if args.org is not None and not printed_org:
        sys.stderr.write("Unable to find the org you set.\n")
        sys.exit(1)
