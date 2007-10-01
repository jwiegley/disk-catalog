#import <Foundation/Foundation.h>

#include <getopt.h>

#import "CMDFind2Controller.h"

static void usage(void);

int main (int argc, const char * argv[])
{
NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];

CMDFind2Controller *theController = [[[CMDFind2Controller alloc] init] autorelease];

int format = MyController_OutputFormatNormal;
struct option longopts[] = {
	{ "xml", no_argument, &format, MyController_OutputFormatXML },
	{ "null", no_argument,  &format, MyController_OutputFormatNullDelimited },
	{ "onlyin",  required_argument, NULL, 'o' },
	{ "limit", required_argument, NULL, 'l' },
	{ NULL, 0, NULL, 0 }
	};
int ch;
while ((ch = getopt_long_only(argc, (char * const *)argv, "0", longopts, NULL)) != -1)
	{
	switch (ch)
		{
		case 'o':
			{
			NSString *thePath = [NSString stringWithUTF8String:optarg];
			[[theController query] setSearchScopes:[NSArray arrayWithObject:thePath]];
			}
			break;
		case 'l':
			[theController setLimit:atoi(optarg)];
			break;
		case '0':
			format = MyController_OutputFormatNullDelimited;
			break;
		case 0:
			break;
		default:
			usage();
		}
	}
argc -= optind;
argv += optind;

[theController setOutputFormat:format];

NSMutableArray *theArguments = [NSMutableArray array];
int N;
for (N = 0; N != argc; ++N)
	[theArguments addObject:[NSString stringWithCString:argv[N] encoding:NSUTF8StringEncoding]];

NSString *thePredicateString = [theArguments componentsJoinedByString:@" "];
NSPredicate *thePredicate = NULL;

@try
	{
	thePredicate = [NSPredicate predicateWithFormat:[NSString stringWithFormat:@"%@", thePredicateString]];
	}
@catch (NSException *localException)
	{
	if ([thePredicateString length] == 0)
		usage();
	thePredicateString = [NSString stringWithFormat:@"kMDItemTextContent == \'%@\'", thePredicateString];
	thePredicate = [NSPredicate predicateWithFormat:[NSString stringWithFormat:@"%@", thePredicateString]];
	fprintf(stderr, "Could not compile predicate, using \"%s\"\n", [thePredicateString UTF8String]);
	}

if (thePredicate != NULL)
	[[theController query] setPredicate:thePredicate];

[theController run];

[pool release];
return 0;
}

static void usage(void)
{
fprintf(stdout, "Usage: mdfind2 [-onlyin <directory>] [-xml|-null|-0] [-limit <int>] query\n");
fprintf(stdout, "\n");
fprintf(stdout, "list the files matching the query\n");
fprintf(stdout, "query can be an expression or a sequence of words\n");
fprintf(stdout, "\n");
fprintf(stdout, "        -onlyin <dir>     Search only within given directory\n");
fprintf(stdout, "        -xml              Output the results as XML\n");
fprintf(stdout, "        -null, -0         Output the results as NUL (``\\0'') separated strings, for use with xargs -0\n");
fprintf(stdout, "        -limit <N>        Limit the output to the first N results\n");
fprintf(stdout, "\n");
fprintf(stdout, "example:  mdfind2 image\n");
fprintf(stdout, "example:  mdfind2 \"kMDItemAuthor == '*MyFavoriteAuthor*'\"\n");
fprintf(stdout, "example:  mdfind2 -xml MyFavoriteAuthor\n");
exit(0);
}
